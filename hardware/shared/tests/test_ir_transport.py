"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredTransmitter: send encodes and writes pulses
- InfraredReceiver: telemetry field ownership and reset (receive behaviour
  is tested through the transceiver in test_ir_transceiver_receive.py)
"""

from array import array

import pytest

from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder
from hardware.shared.ir_codecs.tag import TagInfraredDecoder, TagInfraredEncoder
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transport import (
    InfraredReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)

# ---------------------------------------------------------------------------
# Local copies of wire-frame constants used by tests to nudge pulses.
# ---------------------------------------------------------------------------

_IR_UNIT = 500
_IR_HEADER_MARK = 4000
_IR_HEADER_SPACE = 3000
_IR_LEAD_OUT = 5000
_IR_SPACE_ZERO = _IR_UNIT
_IR_SPACE_ONE = _IR_UNIT * 3
_IR_ERROR_THRESHOLD = _IR_UNIT // 2  # 250 µs


# ---------------------------------------------------------------------------
# Fake ports
# ---------------------------------------------------------------------------


class FakePulseWriter(PulseWriter):
    """Recording fake — stores every write_pulses call for assertions.

    ``is_busy()`` always reports ``False`` (write completes synchronously),
    matching the blocking ``PulseOutWriter``'s externally-observable behaviour.
    """

    def __init__(self):
        self.calls = []

    def write_pulses(self, durations) -> None:
        self.calls.append(list(durations))

    def is_busy(self) -> bool:
        return False


class ControllableFakePulseWriter(PulseWriter):
    """Recording fake whose ``is_busy()`` the test controls directly — simulates
    a non-blocking (e.g. DMA-backed) writer that stays busy across ticks.

    Each ``write_pulses`` call marks the writer busy (as a real DMA-backed
    writer would be the instant a send is kicked off); the test then drives
    ``set_busy(False)`` to simulate the hardware signalling completion.
    """

    def __init__(self):
        self.calls = []
        self._busy = False

    def write_pulses(self, durations) -> None:
        self.calls.append(list(durations))
        self._busy = True

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        self._busy = busy


class FakePulseReader(PulseReader):
    """Replaying fake — drains a queue of pre-loaded pulses one at a time."""

    def __init__(self, pulses=None):
        self._queue = list(pulses) if pulses else []

    def load(self, pulses) -> None:
        """Replace the pending pulse queue."""
        self._queue = list(pulses)

    def read_pulse(self) -> "int | None":
        if self._queue:
            return self._queue.pop(0)
        return None


# ---------------------------------------------------------------------------
# Port contracts
# ---------------------------------------------------------------------------


def test_pulse_writer_base_raises_not_implemented():
    writer = PulseWriter()
    with pytest.raises(NotImplementedError):
        writer.write_pulses(array("H", [500]))


def test_pulse_reader_base_raises_not_implemented():
    reader = PulseReader()
    with pytest.raises(NotImplementedError):
        reader.read_pulse()


def test_pulse_writer_base_is_busy_raises_not_implemented():
    writer = PulseWriter()
    with pytest.raises(NotImplementedError):
        writer.is_busy()


# ---------------------------------------------------------------------------
# IrTransmitGate
# ---------------------------------------------------------------------------


def test_gate_is_not_transmitting_before_any_emission():
    gate = IrTransmitGate()
    assert gate.transmitting is False


def test_gate_is_transmitting_after_begin_transmit():
    gate = IrTransmitGate()
    gate.begin_transmit()
    assert gate.transmitting is True


def test_gate_stops_transmitting_after_matching_end_transmit():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()
    assert gate.transmitting is False


def test_gate_stays_transmitting_until_last_of_concurrent_emissions_ends():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.begin_transmit()
    gate.end_transmit()
    assert gate.transmitting is True

    gate.end_transmit()
    assert gate.transmitting is False


def test_gate_end_transmit_without_begin_does_not_go_negative():
    gate = IrTransmitGate()
    gate.end_transmit()
    assert gate.transmitting is False


def test_gate_should_discard_is_false_before_any_emission():
    gate = IrTransmitGate()
    assert gate.should_discard() is False


def test_gate_should_discard_flushes_once_on_falling_edge_then_stops():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()

    assert gate.should_discard() is True
    assert gate.should_discard() is False


def test_gate_should_discard_is_true_while_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    assert gate.should_discard() is True


def test_gate_should_discard_while_transmitting_preserves_the_falling_edge_flush():
    gate = IrTransmitGate()
    gate.begin_transmit()

    assert gate.should_discard() is True  # short-circuits without touching the latch
    gate.end_transmit()

    assert gate.should_discard() is True  # falling-edge flush still fires
    assert gate.should_discard() is False


# ---------------------------------------------------------------------------
# InfraredTransmitter
# ---------------------------------------------------------------------------


def test_transmitter_encodes_and_writes_pulses():
    writer = FakePulseWriter()
    encoder = AuraInfraredEncoder()
    tx = InfraredTransmitter(writer, encoder)

    payload = b"\xab\xcd"
    tx.send(payload)

    expected = list(encoder.encode(payload))
    assert len(writer.calls) == 1
    assert writer.calls[0] == expected


def test_transmitter_write_pulses_called_once_per_send():
    writer = FakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())
    tx.send(b"\x01")
    tx.send(b"\x02")
    assert len(writer.calls) == 2


def test_transmitter_with_gate_is_transmitting_during_write_pulses():
    class ObservingWriter(PulseWriter):
        def __init__(self, gate):
            self.gate = gate
            self.was_transmitting = None

        def write_pulses(self, durations) -> None:
            self.was_transmitting = self.gate.transmitting

        def is_busy(self) -> bool:
            return False

    gate = IrTransmitGate()
    writer = ObservingWriter(gate)
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)

    tx.send(b"\x01")

    assert writer.was_transmitting is True


def test_transmitter_with_gate_releases_gate_after_send_completes():
    gate = IrTransmitGate()
    writer = FakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)

    tx.send(b"\x01")

    assert gate.transmitting is False
    assert gate.should_discard() is True


# ---------------------------------------------------------------------------
# InfraredTransmitter — queue-one policy and poll
# ---------------------------------------------------------------------------


def test_send_while_idle_starts_write_immediately():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")

    assert len(writer.calls) == 1


def test_send_on_blocking_writer_returns_true_for_synchronous_completion():
    """A blocking writer (FakePulseWriter) finishes inside write_pulses() —
    is_busy() reports False the instant send() checks it back, so the
    payload was fully sent synchronously."""
    writer = FakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    assert tx.send(b"\x01") is True


def test_send_on_nonblocking_writer_returns_false_while_write_still_in_flight():
    """A non-blocking (e.g. DMA-backed) writer goes busy the instant
    write_pulses() is called and stays busy until the test releases it —
    the write started but has not yet completed, so send() must report
    False even though the writer was idle at entry."""
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    assert tx.send(b"\x01") is False


def test_send_while_busy_buffers_and_does_not_start_a_write():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # starts the write; writer reports busy afterward
    writer.calls.clear()

    tx.send(b"\x02")  # writer still busy — must buffer, not start a write

    assert len(writer.calls) == 0


def test_send_while_busy_returns_false():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # starts the write; writer reports busy afterward

    assert tx.send(b"\x02") is False


def test_send_while_busy_returns_false_for_a_third_queued_payload():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # starts the write; writer reports busy afterward
    tx.send(b"\x02")  # appended to the queue

    assert tx.send(b"\x03") is False  # also appended — still False


def test_queued_sends_drain_in_fifo_order_across_polls():
    """A burst of sends behind a busy writer all transmit, oldest first,
    none dropped and none skipped."""
    writer = ControllableFakePulseWriter()
    encoder = AuraInfraredEncoder()
    tx = InfraredTransmitter(writer, encoder)

    tx.send(b"\x01")  # starts the write; writer reports busy afterward
    tx.send(b"\x02")  # queued
    tx.send(b"\x03")  # queued after \x02 — FIFO, not a replacement

    writer.set_busy(False)
    tx.poll()  # starts \x02, the oldest queued payload
    assert writer.calls[-1] == list(encoder.encode(b"\x02"))

    writer.set_busy(False)
    tx.poll()  # starts \x03
    assert writer.calls[-1] == list(encoder.encode(b"\x03"))

    # initial \x01 + \x02 + \x03 — every payload transmitted exactly once
    assert len(writer.calls) == 3


def test_poll_does_nothing_while_writer_is_busy():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")
    tx.send(b"\x02")  # buffered
    writer.calls.clear()

    tx.poll()  # writer still busy — must not start the pending payload

    assert len(writer.calls) == 0


def test_poll_starts_pending_payload_once_writer_reports_idle():
    writer = ControllableFakePulseWriter()
    encoder = AuraInfraredEncoder()
    tx = InfraredTransmitter(writer, encoder)

    tx.send(b"\x01")
    tx.send(b"\x02")  # buffered
    writer.calls.clear()

    writer.set_busy(False)
    tx.poll()

    assert len(writer.calls) == 1
    assert writer.calls[0] == list(encoder.encode(b"\x02"))


def test_poll_pops_queued_payload_after_starting_it():
    """A second poll with nothing newly queued must not re-send."""
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")
    tx.send(b"\x02")  # buffered
    writer.set_busy(False)
    tx.poll()  # starts \x02
    writer.calls.clear()

    tx.poll()  # nothing pending — must be a no-op

    assert len(writer.calls) == 0


def test_encoder_runs_once_per_transmitted_payload_not_per_tick():
    class CountingEncoder(AuraInfraredEncoder):
        def __init__(self):
            self.encode_calls = 0

        def encode(self, data):
            self.encode_calls += 1
            return super().encode(data)

    writer = ControllableFakePulseWriter()
    encoder = CountingEncoder()
    tx = InfraredTransmitter(writer, encoder)

    tx.send(b"\x01")  # encodes once, starts the write
    tx.send(b"\x02")  # queued raw bytes — no encode yet
    tx.poll()  # writer still busy — no encode
    tx.poll()  # still busy — no encode

    assert encoder.encode_calls == 1

    writer.set_busy(False)
    tx.poll()  # writer now idle — starts queued \x02, encodes once

    assert encoder.encode_calls == 2


def test_encoder_runs_once_per_payload_across_multiple_queued_payloads():
    """Verified with more than one queued payload, not just one: each item's
    encode fires exactly when its own write starts, never earlier or twice."""

    class CountingEncoder(AuraInfraredEncoder):
        def __init__(self):
            self.encode_calls = 0

        def encode(self, data):
            self.encode_calls += 1
            return super().encode(data)

    writer = ControllableFakePulseWriter()
    encoder = CountingEncoder()
    tx = InfraredTransmitter(writer, encoder)

    tx.send(b"\x01")  # encodes once, starts the write
    tx.send(b"\x02")  # queued — no encode yet
    tx.send(b"\x03")  # queued — no encode yet

    assert encoder.encode_calls == 1

    writer.set_busy(False)
    tx.poll()  # starts \x02, encodes once
    assert encoder.encode_calls == 2

    writer.set_busy(False)
    tx.poll()  # starts \x03, encodes once
    assert encoder.encode_calls == 3


# ---------------------------------------------------------------------------
# InfraredTransmitter — poll() busy/idle return value
# ---------------------------------------------------------------------------


def test_poll_returns_false_when_writer_is_already_idle_and_nothing_pending():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    assert tx.poll() is False


def test_poll_returns_true_while_writer_still_has_a_write_in_flight():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # writer reports busy after write_pulses — DMA in flight

    assert tx.poll() is True


def test_poll_returns_true_after_promoting_a_pending_send_that_starts_busy():
    """The freed writer immediately goes busy again for the promoted send —
    poll() must reflect the writer's state after starting it, not before."""
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # busy
    tx.send(b"\x02")  # buffered

    writer.set_busy(False)  # hardware signals the first write completed
    assert tx.poll() is True  # started \x02, which goes busy again


def test_poll_returns_false_once_writer_frees_up_with_nothing_pending():
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # busy, nothing queued behind it

    writer.set_busy(False)  # hardware signals completion
    assert tx.poll() is False


def test_gate_fires_end_transmit_synchronously_when_writer_finishes_inline():
    """A writer that reports is_busy()==False right after write_pulses (the
    blocking PulseOutWriter) gets end_transmit called inside send(), not poll()."""
    gate = IrTransmitGate()
    writer = FakePulseWriter()  # always reports is_busy() False
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)

    tx.send(b"\x01")

    assert gate.transmitting is False
    assert gate.should_discard() is True  # already armed — fired during send()


def test_gate_defers_end_transmit_to_the_poll_that_first_observes_idle():
    gate = IrTransmitGate()
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder(), gate)

    tx.send(b"\x01")  # writer reports busy after write_pulses — DMA in flight

    assert gate.transmitting is True  # still armed — DMA in flight

    tx.poll()  # writer still busy — gate stays armed

    assert gate.transmitting is True

    writer.set_busy(False)
    tx.poll()  # writer now idle — end_transmit fires here

    assert gate.transmitting is False
    assert gate.should_discard() is True  # falling-edge flush fires, exactly once
    assert gate.should_discard() is False


def test_gate_released_when_writer_raises_on_kick_off_via_send():
    class RaisingWriter(PulseWriter):
        def write_pulses(self, durations) -> None:
            raise RuntimeError("hardware fault")

        def is_busy(self) -> bool:
            return False

    gate = IrTransmitGate()
    tx = InfraredTransmitter(RaisingWriter(), AuraInfraredEncoder(), gate)

    with pytest.raises(RuntimeError):
        tx.send(b"\x01")

    assert gate.transmitting is False
    assert gate.should_discard() is True


def test_queued_send_encode_error_surfaces_in_poll_not_in_send():
    """An encode error on a queued send is fire-and-forget — it surfaces on
    the poll that attempts to start it, not at the send() call."""

    class FlakyEncoder(AuraInfraredEncoder):
        def __init__(self):
            self.calls = 0

        def encode(self, data):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("bad payload")
            return super().encode(data)

    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, FlakyEncoder())

    tx.send(b"\x01")  # encodes fine, starts the write — writer now busy
    tx.send(b"\x02")  # queued — no encode attempted yet, so send() does not raise

    writer.set_busy(False)
    with pytest.raises(ValueError):
        tx.poll()  # the queued send's encode now runs and raises


def test_queued_send_encode_error_drops_only_the_failing_item_and_queue_keeps_draining():
    """Items queued after a failing payload are untouched by its error and
    are still attempted (and can still succeed) on later polls."""

    class FlakyEncoder(AuraInfraredEncoder):
        def __init__(self):
            self.calls = 0

        def encode(self, data):
            self.calls += 1
            if data == b"\x02":
                raise ValueError("bad payload")
            return super().encode(data)

    writer = ControllableFakePulseWriter()
    encoder = FlakyEncoder()
    tx = InfraredTransmitter(writer, encoder)

    tx.send(b"\x01")  # encodes fine, starts the write — writer now busy
    tx.send(b"\x02")  # queued — will fail to encode
    tx.send(b"\x03")  # queued after the failing payload

    writer.set_busy(False)
    with pytest.raises(ValueError):
        tx.poll()  # \x02's encode raises; \x02 is dropped, not retried

    writer.set_busy(False)
    tx.poll()  # queue keeps draining — \x03 starts and succeeds

    assert writer.calls[-1] == list(encoder.encode(b"\x03"))


# ---------------------------------------------------------------------------
# InfraredTransmitter — set_encoder
# ---------------------------------------------------------------------------


def test_set_encoder_encodes_a_queued_payload_through_the_new_encoder():
    """A payload queued behind a busy writer, then swapped to a different
    codec family before it starts, must encode with the new encoder — proof
    that set_encoder applies to not-yet-started payloads."""
    writer = ControllableFakePulseWriter()
    tx = InfraredTransmitter(writer, AuraInfraredEncoder())

    tx.send(b"\x01")  # starts under the Aura encoder; writer goes busy
    tx.send(b"\x02")  # queued — not yet encoded

    new_encoder = TagInfraredEncoder()
    tx.set_encoder(new_encoder)

    writer.set_busy(False)
    tx.poll()  # starts the queued payload — must encode under the new encoder

    assert writer.calls[-1] == list(new_encoder.encode(b"\x02"))


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry ownership and reset
#
# Receive behaviour is tested through the transceiver in
# test_ir_transceiver_receive.py. What stays here has no transceiver route.
# ---------------------------------------------------------------------------


def _make_receiver(num_readers, decoder_factory=AuraInfraredDecoder):
    """Build an InfraredReceiver over ``num_readers`` independent FakePulseReaders."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredReceiver(list(readers), decoder_factory)
    return rx, readers


@pytest.fixture
def recording_tag_decoder():
    """A Tag decoder class that records every instance built, paired with that
    record, so a test can reach the decoders a receiver built for itself."""
    built: list[TagInfraredDecoder] = []

    class RecordingTagDecoder(TagInfraredDecoder):
        def __init__(self):
            super().__init__()
            built.append(self)

    return RecordingTagDecoder, built


def test_ir_telemetry_field_ownership_partitions_every_snapshot_field_with_no_overlap():
    """Each IrTelemetrySnapshot field has exactly one declared owner —
    InfraredDecoder, PulseReader, or InfraredReceiver. A counter with no
    owner (missing from the union) or two owners (present in more than one
    tuple) fails this test."""
    owned_field_tuples = [
        InfraredDecoder.OWNED_TELEMETRY_FIELDS,
        PulseReader.OWNED_TELEMETRY_FIELDS,
        InfraredReceiver.OWNED_TELEMETRY_FIELDS,
    ]

    union: set[str] = set()
    for fields in owned_field_tuples:
        assert union.isdisjoint(fields), f"{fields} overlaps an already-claimed field"
        union.update(fields)

    assert union == set(IrTelemetrySnapshot.FIELDS)


@pytest.mark.parametrize("num_readers", [1, 2])
def test_receiver_reset_telemetry_zeroes_every_counter_telemetry_reports(
    num_readers, recording_tag_decoder
):
    """Read/reset symmetry: whatever telemetry() reports, reset_telemetry()
    zeroes — checked generically across every declared counter on every
    reader and decoder, so a newly added counter is covered automatically."""
    # Receiver seam: reset_telemetry has no route through the transceiver.
    decoder_factory, built = recording_tag_decoder
    rx, readers = _make_receiver(num_readers, decoder_factory)
    for name in InfraredDecoder.OWNED_TELEMETRY_FIELDS:
        for decoder in built:
            setattr(decoder, name, 7)
    for name in PulseReader.OWNED_TELEMETRY_FIELDS:
        for reader in readers:
            setattr(reader, name, 7)
    for name in InfraredReceiver.OWNED_TELEMETRY_FIELDS:
        setattr(rx, name, 7)

    before = rx.telemetry()
    assert all(getattr(before, field) >= 7 for field in IrTelemetrySnapshot.FIELDS)

    rx.reset_telemetry()

    after = rx.telemetry()
    assert all(getattr(after, field) == 0 for field in IrTelemetrySnapshot.FIELDS)


def test_receiver_telemetry_line_reports_again_after_reset_telemetry():
    """reset_telemetry() clears the change-gate baseline along with the counters."""
    # Receiver seam: reset_telemetry has no route through the transceiver.
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    rx.reset_telemetry()

    assert rx.telemetry_line() is not None
