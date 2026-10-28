"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredTransmitter: send encodes and writes pulses
- InfraredReceiver: receives over one or many readers, picking the packet
  with the lowest error margin, and allocates nothing per tick
"""

import tracemalloc

import pytest

from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder
from hardware.shared.ir_codecs.tag import TAG_PREAMBLE, TagInfraredDecoder, TagInfraredEncoder
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
        writer.write_pulses([500])


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


def _reordered_snapshot_init(
    self,
    packets_surfaced,
    pulses_seen,
    buffer_full_on_poll,
    packets_started,
    preamble_reject,
    mark_reject,
    space_reject,
    packets_completed,
    pulses_dropped_transmitting,
):
    """A stand-in ``IrTelemetrySnapshot.__init__`` with two parameters
    (``pulses_seen``/``packets_surfaced``) swapped relative to ``FIELDS``.

    Used to simulate a future ``FIELDS`` reorder without touching the real
    class. A ``telemetry()`` that still builds positional arguments in the
    old order would silently swap these two counters; one that builds by
    keyword is unaffected."""
    self.pulses_seen = pulses_seen
    self.packets_surfaced = packets_surfaced
    self.buffer_full_on_poll = buffer_full_on_poll
    self.packets_started = packets_started
    self.preamble_reject = preamble_reject
    self.mark_reject = mark_reject
    self.space_reject = space_reject
    self.packets_completed = packets_completed
    self.pulses_dropped_transmitting = pulses_dropped_transmitting


# ---------------------------------------------------------------------------
# InfraredReceiver — fixtures
# ---------------------------------------------------------------------------


def _encode_pulses(payload: bytes):
    return list(AuraInfraredEncoder().encode(payload))


def _make_receiver(num_readers, decoder_class=AuraInfraredDecoder, gate=None):
    """Build an InfraredReceiver over ``num_readers`` independent FakePulseReaders."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredReceiver(readers, decoder_class, gate)
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


# ---------------------------------------------------------------------------
# InfraredReceiver — receiving packets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_readers", [1, 3])
def test_receiver_returns_none_when_no_reader_has_pulses(num_readers):
    rx, _ = _make_receiver(num_readers)

    assert rx.receive() is None


def test_receiver_returns_payload_after_complete_packet():
    payload = b"\xde\xad"
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(payload))

    assert rx.receive() == bytearray(payload)


def test_receiver_assembles_a_packet_fed_across_several_ticks():
    payload = b"\xbe\xef"
    rx, readers = _make_receiver(1)

    result = None
    for pulse in _encode_pulses(payload):
        readers[0].load([pulse])
        result = rx.receive()
        if result is not None:
            break

    assert result == bytearray(payload)


def test_receiver_returns_payload_when_one_of_several_readers_has_a_complete_packet():
    payload = b"\x11\x22"
    rx, readers = _make_receiver(2)
    readers[1].load(_encode_pulses(payload))

    assert rx.receive() == bytearray(payload)


def test_receiver_surfaces_at_most_one_packet_per_reader_per_tick():
    """Two back-to-back packets buffered on one reader surface one tick apart."""
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(b"\x01") + _encode_pulses(b"\x02"))

    assert rx.receive() == bytearray(b"\x01")
    assert rx.receive() == bytearray(b"\x02")


# ---------------------------------------------------------------------------
# InfraredReceiver — lowest-error-margin selection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clean_index", [0, 1])
def test_receiver_picks_the_packet_with_the_lowest_error_margin(clean_index):
    payload = b"\xab"
    pulses_clean = _encode_pulses(payload)
    pulses_noisy = _encode_pulses(payload)
    pulses_noisy[3] += 80  # 80 µs deviation — still within threshold

    rx, readers = _make_receiver(2)
    readers[clean_index].load(pulses_clean)
    readers[1 - clean_index].load(pulses_noisy)

    assert rx.receive() == bytearray(payload)
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[clean_index]


def test_receiver_picks_the_first_reader_on_an_error_margin_tie():
    payload = b"\x5a"
    rx, readers = _make_receiver(3)
    readers[1].load(_encode_pulses(payload))
    readers[2].load(_encode_pulses(payload))

    rx.receive()

    assert rx.last_best_receiver is readers[1]


def test_receiver_reports_the_winning_readers_signal():
    payload = b"\x99"
    rx, readers = _make_receiver(3)
    readers[2].load(_encode_pulses(payload))

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[2]


def test_receiver_reports_no_signal_before_the_first_packet():
    rx, _ = _make_receiver(2)

    assert rx.last_signal_strength is None
    assert rx.last_error_margin is None
    assert rx.last_best_receiver is None


def test_single_reader_receiver_reports_signal_but_no_best_receiver():
    """With one reader there is no pick to report, but the signal still is."""
    rx, readers = _make_receiver(1)
    readers[0].load(_encode_pulses(b"\x42"))

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is None


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry counters
# ---------------------------------------------------------------------------


def test_receiver_pulses_seen_counts_every_pulse_across_readers_and_ticks():
    rx, readers = _make_receiver(2)
    readers[0].load([100, 200])
    readers[1].load([300])
    rx.receive()
    readers[0].load([400])
    rx.receive()

    assert rx.telemetry().pulses_seen == 4


def test_receiver_packets_surfaced_counts_only_winning_packets():
    rx, readers = _make_receiver(2)
    readers[0].load(_encode_pulses(b"\x01"))
    rx.receive()
    readers[1].load([100, 200])  # noise, no packet
    rx.receive()

    assert rx.telemetry().packets_surfaced == 1


def test_receiver_telemetry_sums_decoder_counters_across_readers():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    rx, readers = _make_receiver(2, TagInfraredDecoder)
    readers[0].load(bad_preamble)
    readers[1].load(bad_preamble)

    rx.receive()

    assert rx.telemetry().preamble_reject == 2


def test_receiver_telemetry_sums_buffer_full_on_poll_across_readers():
    rx, readers = _make_receiver(3)
    readers[0].buffer_full_on_poll = 2
    readers[2].buffer_full_on_poll = 5

    assert rx.telemetry().buffer_full_on_poll == 7


def test_receiver_packets_completed_can_exceed_surfaced_on_simultaneous_wins():
    """Dedup, not loss: two decoders independently completing the same shot in
    one tick both count toward (summed) packets_completed, but only the
    lowest-error-margin winner surfaces from receive()."""
    pulses = list(TagInfraredEncoder().encode(bytearray([0x10])))
    rx, readers = _make_receiver(3, TagInfraredDecoder)
    readers[0].load(pulses)
    readers[2].load(pulses)

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.packets_completed == 2
    assert snapshot.packets_surfaced == 1


def test_receiver_telemetry_survives_a_fields_reorder(monkeypatch):
    """A ``FIELDS`` reorder (simulated here by an ``IrTelemetrySnapshot``
    constructor with two parameters swapped) must not swap counters — proves
    ``telemetry()`` builds the snapshot by keyword, not position."""
    monkeypatch.setattr(IrTelemetrySnapshot, "__init__", _reordered_snapshot_init)
    pulses = _encode_pulses(b"\xde\xad")
    rx, readers = _make_receiver(1)
    readers[0].load(pulses)

    rx.receive()
    snapshot = rx.telemetry()

    assert snapshot.pulses_seen == len(pulses)
    assert snapshot.packets_surfaced == 1


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
    decoder_class, built = recording_tag_decoder
    rx, readers = _make_receiver(num_readers, decoder_class)
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


# ---------------------------------------------------------------------------
# InfraredReceiver — telemetry_line() change-gating
# ---------------------------------------------------------------------------


def test_receiver_telemetry_line_reports_on_first_call():
    """The very first call has no prior baseline, so it always reports."""
    rx, _ = _make_receiver(1)

    assert rx.telemetry_line() is not None


def test_receiver_telemetry_line_is_none_when_nothing_changed():
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    assert rx.telemetry_line() is None


def test_receiver_telemetry_line_reports_the_pipeline_format_after_a_packet():
    pulses = _encode_pulses(b"\x42")
    rx, readers = _make_receiver(1)
    readers[0].load(pulses)

    rx.receive()
    line = rx.telemetry_line()

    assert line == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_receiver_telemetry_line_reports_again_after_reset_telemetry():
    """reset_telemetry() clears the change-gate baseline along with the counters."""
    rx, _ = _make_receiver(1)
    rx.telemetry_line()

    rx.reset_telemetry()

    assert rx.telemetry_line() is not None


# ---------------------------------------------------------------------------
# InfraredReceiver — gate-driven self-echo suppression
# ---------------------------------------------------------------------------


def test_receiver_drops_echo_on_every_reader_while_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_receiver(3, gate=gate)
    payload = b"\x33"
    readers[0].load(_encode_pulses(payload))
    readers[2].load(_encode_pulses(payload))

    assert rx.receive() is None


def test_receiver_counts_dropped_pulses_from_every_reader_apart_from_pulses_seen():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load([100, 200])
    readers[1].load([300, 400, 500])

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.pulses_dropped_transmitting == 5
    assert snapshot.pulses_seen == 0


def test_receiver_partial_decode_in_progress_when_transmit_begins_is_reset_on_every_reader():
    pulses = _encode_pulses(b"\x44")
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load(pulses[:mid])
    readers[1].load(pulses[:mid])
    rx.receive()  # both readers mid-decode, gate idle

    gate.begin_transmit()
    rx.receive()  # the drop resets both decoders, even with nothing buffered
    gate.end_transmit()
    rx.receive()  # consume the flush

    readers[0].load(pulses[mid:])
    readers[1].load(pulses[mid:])
    assert rx.receive() is None


def test_receiver_partial_decode_in_progress_when_transmit_ends_is_reset():
    """A decode mid-flight at the falling-edge flush does not survive it either."""
    pulses = _encode_pulses(b"\xde\xad")
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    rx, readers = _make_receiver(1, gate=gate)

    gate.begin_transmit()
    readers[0].load(pulses[:mid])  # echo pulses captured mid-emission
    rx.receive()

    gate.end_transmit()
    rx.receive()  # falling-edge flush resets the decoder

    readers[0].load(pulses[mid:])
    assert rx.receive() is None


def test_receiver_falling_edge_discards_the_buffered_echo_tail():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    readers[0].load([111, 222])  # buffered echo tail

    rx.receive()

    assert rx.telemetry().pulses_dropped_transmitting == 2


def test_receiver_decodes_normally_after_the_one_shot_falling_edge_flush():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()
    rx, readers = _make_receiver(2, gate=gate)
    rx.receive()  # consumes the one-shot flush

    payload = b"\x21"
    readers[1].load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


# ---------------------------------------------------------------------------
# InfraredReceiver — no per-tick allocation in polled path
# ---------------------------------------------------------------------------


def _allocations_in_ir_transport_over_100_receives(rx):
    """Return the ir_transport.py allocation growth across 100 ``receive()`` calls.

    Uses ``tracemalloc`` snapshot comparison rather than ``gc.get_count()`` so
    that transient (immediately-freed) per-tick allocations are also detected.
    Only allocations attributed to ``ir_transport.py`` are checked — this
    filters out tracemalloc's own internal overhead.
    """
    # Warm up: let any one-time setup allocations settle
    for _ in range(5):
        rx.receive()

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for _ in range(100):
        rx.receive()

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    return [
        stat
        for stat in after.compare_to(before, "lineno")
        if stat.traceback[0].filename.endswith("/ir_transport.py") and stat.size_diff > 0
    ]


@pytest.mark.parametrize("num_readers", [1, 3])
def test_receiver_receive_allocates_nothing_per_tick_when_no_packet(num_readers):
    rx, _ = _make_receiver(num_readers)

    diff = _allocations_in_ir_transport_over_100_receives(rx)

    assert not diff, f"Unexpected allocations in ir_transport.py during idle receive: {diff}"


def test_receiver_drop_path_allocates_nothing_per_tick():
    """The gated drain-but-discard path must not allocate per tick either.

    Uses readers with nothing buffered (the common steady-state tick while
    emitting) so the only thing exercised repeatedly is the drain loop and
    the gate check — not a growing counter, whose own integer-widening as it
    crosses CPython's small-int cache is an unrelated, unavoidable artifact
    of any incrementing counter and would otherwise produce a false positive.
    """
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, _ = _make_receiver(3, gate=gate)

    diff = _allocations_in_ir_transport_over_100_receives(rx)

    assert not diff, f"Unexpected allocations in ir_transport.py during drop receive: {diff}"


# ---------------------------------------------------------------------------
# InfraredReceiver — set_decoder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_readers", [1, 2])
def test_receiver_set_decoder_decodes_through_the_new_decoder_type(num_readers):
    """A packet encoded for the Tag protocol only decodes once the receiver's
    decoders are swapped from Aura to Tag."""
    payload = bytearray([0x10])
    rx, readers = _make_receiver(num_readers)

    rx.set_decoder(TagInfraredDecoder())
    readers[-1].load(list(TagInfraredEncoder().encode(payload)))

    assert rx.receive() == payload


def test_receiver_set_decoder_gives_each_reader_its_own_fresh_decoder(recording_tag_decoder):
    """set_decoder builds one new decoder per reader and never installs the
    instance it was handed, so no decode state is shared between readers."""
    decoder_class, built = recording_tag_decoder
    rx, _ = _make_receiver(2)
    handed = decoder_class()

    rx.set_decoder(handed)

    built_by_receiver = [d for d in built if d is not handed]
    assert len(built_by_receiver) == 2


def test_receiver_set_decoder_keeps_a_partial_decode_on_one_reader_from_corrupting_another():
    payload = bytearray([0x30])
    pulses = list(TagInfraredEncoder().encode(payload))
    mid = len(pulses) // 2
    rx, readers = _make_receiver(2)
    rx.set_decoder(TagInfraredDecoder())

    readers[0].load(pulses[:mid])  # reader 0 left mid-decode, never completes
    rx.receive()

    readers[1].load(pulses)  # reader 1's independent, complete packet
    assert rx.receive() == payload


def test_receiver_set_decoder_reports_telemetry_from_the_new_decoders():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    rx, readers = _make_receiver(1)
    rx.set_decoder(TagInfraredDecoder())
    readers[0].load(bad_preamble)

    rx.receive()

    assert rx.telemetry().preamble_reject == 1
