"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredTransmitter: send encodes and writes pulses
- InfraredSingleReceiver: round-trip receive with fake ports
- InfraredMultiReceiver: picks the packet with the lowest error margin
- InfraredMultiReceiver.receive() allocates nothing per tick in the polled path
"""

import tracemalloc

import pytest

from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder, InfraredDecoder
from hardware.shared.ir_telemetry import IrTelemetrySnapshot
from hardware.shared.ir_transport import (
    InfraredMultiReceiver,
    InfraredReceiver,
    InfraredSingleReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)
from hardware.shared.tag_protocol import TAG_PREAMBLE, TagInfraredDecoder, TagInfraredEncoder

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
    """Depth-counted: begin, begin, end leaves one emission still in flight."""
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


def test_transmitter_without_gate_behaviour_is_unchanged():
    writer = FakePulseWriter()
    encoder = AuraInfraredEncoder()
    tx = InfraredTransmitter(writer, encoder)

    payload = b"\xab\xcd"
    tx.send(payload)

    assert writer.calls[0] == list(encoder.encode(payload))


def test_transmitter_with_gate_is_transmitting_during_write_pulses():
    """The gate must be armed for the duration of the (blocking) write call."""

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
# InfraredReceiver base contract
# ---------------------------------------------------------------------------


def test_receiver_base_raises_not_implemented():
    rx = InfraredReceiver()
    with pytest.raises(NotImplementedError):
        rx.receive()


def test_receiver_base_telemetry_defaults_every_counter_to_zero():
    rx = InfraredReceiver()

    snapshot = rx.telemetry()

    assert snapshot.pulses_seen == 0
    assert snapshot.packets_surfaced == 0
    assert snapshot.packets_started == 0
    assert snapshot.packets_completed == 0
    assert snapshot.preamble_reject == 0
    assert snapshot.mark_reject == 0
    assert snapshot.space_reject == 0
    assert snapshot.buffer_full_on_poll == 0
    assert snapshot.pulses_dropped_transmitting == 0


def test_bare_receiver_subclass_satisfies_telemetry_contract_with_no_overrides():
    """A fake receiver with no telemetry code still returns a real snapshot —
    the base default reads counters generically off ``self``."""

    class FakeReceiver(InfraredReceiver):
        def receive(self):
            return None

    rx = FakeReceiver()
    rx.pulses_seen = 5

    assert rx.telemetry().pulses_seen == 5
    assert rx.telemetry().packets_completed == 0


# ---------------------------------------------------------------------------
# InfraredSingleReceiver — round-trip
# ---------------------------------------------------------------------------


def _encode_pulses(payload: bytes):
    return list(AuraInfraredEncoder().encode(payload))


def test_single_receiver_returns_none_when_no_pulses_available():
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    assert rx.receive() is None


def test_single_receiver_returns_payload_after_complete_packet():
    payload = b"\xde\xad"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    result = rx.receive()
    assert result == bytearray(payload)


def test_single_receiver_returns_payload_across_multiple_receive_calls():
    """Partial pulses fed across ticks still assemble a full packet."""
    payload = b"\xbe\xef"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    result = None
    for pulse in pulses:
        reader.load([pulse])
        result = rx.receive()
        if result is not None:
            break

    assert result == bytearray(payload)


def test_single_receiver_telemetry_after_successful_receive():
    payload = b"\x42"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is None  # single receiver always returns None


def test_single_receiver_telemetry_is_none_before_first_packet():
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    assert rx.last_signal_strength is None
    assert rx.last_error_margin is None
    assert rx.last_best_receiver is None


# ---------------------------------------------------------------------------
# InfraredSingleReceiver — telemetry counters
# ---------------------------------------------------------------------------


def test_single_receiver_pulses_seen_counts_every_drained_pulse():
    payload = b"\xde\xad"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader(pulses)
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()

    assert rx.telemetry().pulses_seen == len(pulses)


def test_single_receiver_pulses_seen_accumulates_across_receive_calls():
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    reader.load([100, 200])
    rx.receive()
    reader.load([300])
    rx.receive()

    assert rx.telemetry().pulses_seen == 3


def test_single_receiver_packets_surfaced_increments_on_successful_receive():
    payload = b"\x01"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()
    rx.receive()  # second call: no more pulses, no new packet

    assert rx.telemetry().packets_surfaced == 1


def test_single_receiver_delegates_decoder_counters_from_tag_decoder():
    """The whole path reads off ir_receiver — decoder counters surface here."""
    decoder = TagInfraredDecoder()
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    reader = FakePulseReader(bad_preamble)
    rx = InfraredSingleReceiver(reader, decoder)

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.preamble_reject == decoder.preamble_reject == 1
    assert snapshot.packets_started == decoder.packets_started == 0
    assert snapshot.packets_completed == decoder.packets_completed == 0
    assert snapshot.mark_reject == decoder.mark_reject == 0
    assert snapshot.space_reject == decoder.space_reject == 0


def test_single_receiver_delegates_buffer_full_on_poll_from_reader():
    reader = FakePulseReader()
    reader.buffer_full_on_poll = 3
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    assert rx.telemetry().buffer_full_on_poll == 3


def test_single_receiver_reset_telemetry_zeroes_whole_ir_path():
    decoder = TagInfraredDecoder()
    payload = [*list(TagInfraredEncoder().encode(bytearray([0x10]))), TAG_PREAMBLE[0]]
    reader = FakePulseReader(payload)
    rx = InfraredSingleReceiver(reader, decoder)
    reader.buffer_full_on_poll = 2
    rx.receive()

    rx.reset_telemetry()

    snapshot = rx.telemetry()
    assert snapshot.pulses_seen == 0
    assert snapshot.packets_surfaced == 0
    assert snapshot.packets_started == 0
    assert snapshot.packets_completed == 0
    assert snapshot.preamble_reject == 0
    assert snapshot.mark_reject == 0
    assert snapshot.space_reject == 0
    assert snapshot.buffer_full_on_poll == 0
    assert decoder.packets_started == 0
    assert decoder.packets_completed == 0
    assert reader.buffer_full_on_poll == 0


def test_single_receiver_telemetry_survives_a_fields_reorder(monkeypatch):
    """A ``FIELDS`` reorder (simulated here by an ``IrTelemetrySnapshot``
    constructor with two parameters swapped) must not swap counters — proves
    ``telemetry()`` builds the snapshot by keyword, not position."""
    monkeypatch.setattr(IrTelemetrySnapshot, "__init__", _reordered_snapshot_init)
    payload = b"\xde\xad"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()
    snapshot = rx.telemetry()

    assert snapshot.pulses_seen == rx.pulses_seen
    assert snapshot.packets_surfaced == rx.packets_surfaced


# ---------------------------------------------------------------------------
# InfraredSingleReceiver — telemetry_line() change-gating
# ---------------------------------------------------------------------------


def test_single_receiver_telemetry_line_reports_on_first_call():
    """The very first call has no prior baseline, so it always reports."""
    rx = InfraredSingleReceiver(FakePulseReader(), AuraInfraredDecoder())

    assert rx.telemetry_line() is not None


def test_single_receiver_telemetry_line_is_none_when_nothing_changed():
    rx = InfraredSingleReceiver(FakePulseReader(), AuraInfraredDecoder())
    rx.telemetry_line()

    assert rx.telemetry_line() is None


def test_single_receiver_telemetry_line_reports_the_pipeline_format_after_a_packet():
    payload = b"\x42"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader(pulses)
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()
    line = rx.telemetry_line()

    assert line == (
        "ir: pulses_seen=" + str(len(pulses)) + " buffer_full_on_poll=0 "
        "packets_started=0 preamble_reject=0 mark_reject=0 space_reject=0 "
        "packets_completed=0 packets_surfaced=1 pulses_dropped_transmitting=0"
    )


def test_single_receiver_telemetry_line_reports_again_after_reset_telemetry():
    """reset_telemetry() clears the change-gate baseline along with the counters."""
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())
    rx.telemetry_line()

    rx.reset_telemetry()

    assert rx.telemetry_line() is not None


# ---------------------------------------------------------------------------
# InfraredSingleReceiver — gate-driven self-echo suppression
# ---------------------------------------------------------------------------


def test_single_receiver_without_gate_behaviour_is_unchanged():
    payload = b"\xde\xad"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    assert rx.receive() == bytearray(payload)


def test_single_receiver_drops_pulses_while_gate_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    payload = b"\xde\xad"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)

    assert rx.receive() is None


def test_single_receiver_drop_increments_dropped_counter_not_pulses_seen():
    gate = IrTransmitGate()
    gate.begin_transmit()
    payload = b"\xde\xad"
    pulses = _encode_pulses(payload)
    reader = FakePulseReader(pulses)
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.pulses_dropped_transmitting == len(pulses)
    assert snapshot.pulses_seen == 0


def test_single_receiver_partial_decode_in_progress_when_transmit_begins_is_reset():
    """Feeding the remainder of a frame after the gate opens does not complete it."""
    payload = b"\xde\xad"
    pulses = _encode_pulses(payload)
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)

    reader.load(pulses[:mid])
    rx.receive()

    gate.begin_transmit()
    rx.receive()  # the drop path resets the decoder even with nothing buffered

    reader.load(pulses[mid:])
    assert rx.receive() is None


def test_single_receiver_partial_decode_in_progress_when_transmit_ends_is_reset():
    """A decode mid-flight at the falling-edge flush does not survive it either."""
    payload = b"\xde\xad"
    pulses = _encode_pulses(payload)
    mid = len(pulses) // 2
    gate = IrTransmitGate()
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)

    gate.begin_transmit()
    reader.load(pulses[:mid])  # echo pulses captured mid-emission
    rx.receive()

    gate.end_transmit()
    rx.receive()  # falling-edge flush resets the decoder

    reader.load(pulses[mid:])
    assert rx.receive() is None


def test_single_receiver_falling_edge_flushes_once_then_decodes_normally():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()

    reader = FakePulseReader([111, 222])  # buffered echo tail
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)

    # First poll after the falling edge: one flush, discards the echo tail.
    assert rx.receive() is None
    assert rx.telemetry().pulses_dropped_transmitting == 2

    # Next poll: gate is fully idle, a genuine packet decodes normally.
    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


def test_single_receiver_gate_idle_does_not_discard_repeatedly():
    """The falling-edge flush is one-shot — a second idle poll must not re-drop."""
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()

    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    rx.receive()  # consumes the one-shot flush

    payload = b"\x09"
    reader.load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


def test_single_receiver_reset_telemetry_zeroes_pulses_dropped_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    reader = FakePulseReader([100, 200])
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder(), gate)
    rx.receive()
    assert rx.telemetry().pulses_dropped_transmitting == 2

    rx.reset_telemetry()

    assert rx.telemetry().pulses_dropped_transmitting == 0


# ---------------------------------------------------------------------------
# InfraredMultiReceiver — lowest-error-margin selection
# ---------------------------------------------------------------------------


def _make_multi_receiver(num_readers):
    """Build a MultiReceiver with ``num_readers`` independent FakePulseReaders."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredMultiReceiver(readers, AuraInfraredDecoder)
    return rx, readers


def test_multi_receiver_returns_none_when_no_readers_have_pulses():
    rx, _ = _make_multi_receiver(3)
    assert rx.receive() is None


def test_multi_receiver_returns_payload_when_one_reader_has_complete_packet():
    payload = b"\x11\x22"
    rx, readers = _make_multi_receiver(2)
    readers[0].load(_encode_pulses(payload))

    result = rx.receive()
    assert result == bytearray(payload)


def test_multi_receiver_picks_packet_with_lower_error_margin():
    """When both readers decode a packet, the lower-error-margin packet wins."""
    payload = b"\xab"
    encoder = AuraInfraredEncoder()
    pulses_good = list(encoder.encode(payload))
    pulses_noisy = list(encoder.encode(payload))
    # Nudge a bit space in the noisy stream to introduce timing error
    pulses_noisy[3] += 80  # 80 µs deviation — still within threshold

    rx, readers = _make_multi_receiver(2)
    readers[0].load(pulses_good)
    readers[1].load(pulses_noisy)

    result = rx.receive()
    assert result == bytearray(payload)
    assert rx.last_error_margin == 0  # perfect packet won
    assert rx.last_best_receiver is readers[0]


def test_multi_receiver_picks_least_noisy_regardless_of_reader_order():
    """Noisy reader first — the cleaner reader should still win."""
    payload = b"\x55"
    encoder = AuraInfraredEncoder()
    pulses_noisy = list(encoder.encode(payload))
    pulses_noisy[3] += 100  # 100 µs timing error
    pulses_clean = list(encoder.encode(payload))

    rx, readers = _make_multi_receiver(2)
    readers[0].load(pulses_noisy)
    readers[1].load(pulses_clean)

    result = rx.receive()
    assert result == bytearray(payload)
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[1]


def test_multi_receiver_telemetry_after_single_decoder_fires():
    payload = b"\x99"
    rx, readers = _make_multi_receiver(3)
    readers[2].load(_encode_pulses(payload))

    rx.receive()

    assert rx.last_signal_strength == 1.0
    assert rx.last_error_margin == 0
    assert rx.last_best_receiver is readers[2]


def test_multi_receiver_telemetry_is_none_before_first_packet():
    rx, _ = _make_multi_receiver(2)
    assert rx.last_signal_strength is None
    assert rx.last_error_margin is None
    assert rx.last_best_receiver is None


# ---------------------------------------------------------------------------
# InfraredMultiReceiver — gate-driven self-echo suppression
# ---------------------------------------------------------------------------


def _make_gated_multi_receiver(num_readers, gate):
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredMultiReceiver(readers, AuraInfraredDecoder, gate)
    return rx, readers


def test_multi_receiver_without_gate_behaviour_is_unchanged():
    payload = b"\x11\x22"
    rx, readers = _make_multi_receiver(2)
    readers[0].load(_encode_pulses(payload))

    assert rx.receive() == bytearray(payload)


def test_multi_receiver_drops_echo_across_all_readers_while_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_gated_multi_receiver(3, gate)
    payload = b"\x33"
    readers[0].load(_encode_pulses(payload))
    readers[2].load(_encode_pulses(payload))

    assert rx.receive() is None


def test_multi_receiver_drop_discards_pulses_from_every_reader():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_gated_multi_receiver(2, gate)
    readers[0].load([100, 200])
    readers[1].load([300, 400, 500])

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.pulses_dropped_transmitting == 5
    assert snapshot.pulses_seen == 0


def test_multi_receiver_drop_resets_every_decoder():
    """A partial decode in any reader does not survive a drop."""
    payload = b"\x44"
    pulses = _encode_pulses(payload)
    mid = len(pulses) // 2

    gate = IrTransmitGate()
    rx, readers = _make_gated_multi_receiver(2, gate)
    readers[0].load(pulses[:mid])
    readers[1].load(pulses[:mid])
    rx.receive()  # both readers mid-decode, gate idle

    gate.begin_transmit()
    rx.receive()  # drop resets both decoders
    gate.end_transmit()
    rx.receive()  # consume the flush

    readers[0].load(pulses[mid:])
    readers[1].load(pulses[mid:])
    assert rx.receive() is None


def test_multi_receiver_falling_edge_flushes_once_then_decodes_normally():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()

    rx, readers = _make_gated_multi_receiver(2, gate)
    readers[0].load([111])  # buffered echo tail

    assert rx.receive() is None  # one-shot flush
    assert rx.telemetry().pulses_dropped_transmitting == 1

    payload = b"\x21"
    readers[1].load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


def test_multi_receiver_reset_telemetry_zeroes_pulses_dropped_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_gated_multi_receiver(2, gate)
    readers[0].load([100])

    rx.receive()
    assert rx.telemetry().pulses_dropped_transmitting == 1

    rx.reset_telemetry()

    assert rx.telemetry().pulses_dropped_transmitting == 0


# ---------------------------------------------------------------------------
# InfraredMultiReceiver — receive-path telemetry (issue #600)
# ---------------------------------------------------------------------------


def test_multi_receiver_pulses_seen_accumulates_across_all_readers():
    rx, readers = _make_multi_receiver(2)
    readers[0].load([100, 200])
    readers[1].load([300])

    rx.receive()

    assert rx.telemetry().pulses_seen == 3


def test_multi_receiver_pulses_seen_accumulates_across_receive_calls():
    rx, readers = _make_multi_receiver(1)
    readers[0].load([100, 200])
    rx.receive()
    readers[0].load([300])
    rx.receive()

    assert rx.telemetry().pulses_seen == 3


def test_multi_receiver_packets_surfaced_increments_on_winning_packet():
    payload = b"\x01"
    rx, readers = _make_multi_receiver(2)
    readers[0].load(_encode_pulses(payload))

    rx.receive()

    assert rx.telemetry().packets_surfaced == 1


def test_multi_receiver_packets_surfaced_does_not_increment_without_a_winner():
    rx, readers = _make_multi_receiver(2)
    readers[0].load([100, 200])

    rx.receive()

    assert rx.telemetry().packets_surfaced == 0


def test_multi_receiver_reset_telemetry_zeroes_pulses_seen_and_packets_surfaced():
    payload = b"\x01"
    rx, readers = _make_multi_receiver(2)
    readers[0].load(_encode_pulses(payload))
    rx.receive()

    rx.reset_telemetry()

    snapshot = rx.telemetry()
    assert snapshot.pulses_seen == 0
    assert snapshot.packets_surfaced == 0


def test_multi_receiver_telemetry_sums_buffer_full_on_poll_across_readers():
    rx, readers = _make_multi_receiver(3)
    readers[0].buffer_full_on_poll = 2
    readers[1].buffer_full_on_poll = 0
    readers[2].buffer_full_on_poll = 5

    assert rx.telemetry().buffer_full_on_poll == 7


def test_multi_receiver_telemetry_survives_a_fields_reorder(monkeypatch):
    """A ``FIELDS`` reorder (simulated here by an ``IrTelemetrySnapshot``
    constructor with two parameters swapped) must not swap counters — proves
    ``telemetry()`` builds the snapshot by keyword, not position."""
    monkeypatch.setattr(IrTelemetrySnapshot, "__init__", _reordered_snapshot_init)
    payload = b"\x01"
    rx, readers = _make_multi_receiver(2)
    readers[0].load(_encode_pulses(payload))

    rx.receive()
    snapshot = rx.telemetry()

    assert snapshot.pulses_seen == rx.pulses_seen
    assert snapshot.packets_surfaced == rx.packets_surfaced


def _make_tag_multi_receiver(num_readers):
    """Build a MultiReceiver wired to ``TagInfraredDecoder``, which (unlike
    ``AuraInfraredDecoder``) tracks packets_started/preamble_reject/etc., so
    the sums below reflect real decoder state rather than fixed zeros."""
    readers = [FakePulseReader() for _ in range(num_readers)]
    rx = InfraredMultiReceiver(readers, TagInfraredDecoder)
    return rx, readers


def test_multi_receiver_telemetry_sums_preamble_reject_across_decoders():
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    rx, readers = _make_tag_multi_receiver(2)
    readers[0].load(bad_preamble)
    readers[1].load(bad_preamble)

    rx.receive()

    assert rx.telemetry().preamble_reject == 2


def test_multi_receiver_packets_completed_can_exceed_surfaced_on_simultaneous_wins():
    """Dedup, not loss: two decoders independently completing the same shot in
    one tick both count toward (summed) packets_completed, but only the
    lowest-error-margin winner surfaces from receive()."""
    pulses = list(TagInfraredEncoder().encode(bytearray([0x10])))
    rx, readers = _make_tag_multi_receiver(3)
    readers[0].load(pulses)
    readers[2].load(pulses)

    rx.receive()

    snapshot = rx.telemetry()
    assert snapshot.packets_completed == 2
    assert snapshot.packets_surfaced == 1


# ---------------------------------------------------------------------------
# InfraredMultiReceiver — no per-tick allocation in polled path
# ---------------------------------------------------------------------------


def test_multi_receiver_receive_allocates_nothing_per_tick_when_no_packet():
    """Calling receive() with no incoming pulses must not allocate heap objects.

    Uses ``tracemalloc`` snapshot comparison rather than ``gc.get_count()`` so
    that transient (immediately-freed) per-tick allocations are also detected.
    Only allocations attributed to ``ir_transport.py`` are checked — this
    filters out tracemalloc's own internal overhead.
    """
    rx, _ = _make_multi_receiver(3)

    # Warm up: let any one-time setup allocations settle
    for _ in range(5):
        rx.receive()

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for _ in range(100):
        rx.receive()

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Filter to lines inside ir_transport.py so tracemalloc's own bookkeeping
    # overhead does not produce false positives.
    diff = [
        stat
        for stat in after.compare_to(before, "lineno")
        if "ir_transport.py" in stat.traceback[0].filename and stat.size_diff > 0
    ]
    assert not diff, f"Unexpected allocations in ir_transport.py during idle receive: {diff}"


def test_multi_receiver_drop_path_allocates_nothing_per_tick():
    """The gated drain-but-discard path must not allocate per tick either.

    Uses readers with nothing buffered (the common steady-state tick while
    emitting) so the only thing exercised repeatedly is the drain loop and
    the gate check — not a growing counter, whose own integer-widening as it
    crosses CPython's small-int cache is an unrelated, unavoidable artifact
    of any incrementing counter and would otherwise produce a false positive.
    """
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, _ = _make_gated_multi_receiver(3, gate)

    # Warm up: let any one-time setup allocations settle
    for _ in range(5):
        rx.receive()

    tracemalloc.start()
    before = tracemalloc.take_snapshot()

    for _ in range(100):
        rx.receive()

    after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diff = [
        stat
        for stat in after.compare_to(before, "lineno")
        if stat.traceback[0].filename.endswith("/ir_transport.py") and stat.size_diff > 0
    ]
    assert not diff, f"Unexpected allocations in ir_transport.py during drop receive: {diff}"


# ---------------------------------------------------------------------------
# IR telemetry field ownership (issue #730) — the reset bug is unrepresentable
# ---------------------------------------------------------------------------


def test_multi_receiver_reset_telemetry_zeroes_buffer_full_on_poll_across_readers():
    """Regression: a multi-receiver reset must not leave buffer_full_on_poll
    stale. Reading (telemetry()) and resetting (reset_telemetry()) both walk
    every reader now, so a reset can no longer zero the decoders while
    leaving the readers' counts to be reported as fresh."""
    rx, readers = _make_multi_receiver(2)
    readers[0].buffer_full_on_poll = 3
    readers[1].buffer_full_on_poll = 4

    rx.reset_telemetry()

    assert rx.telemetry().buffer_full_on_poll == 0


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


def _set_every_owned_counter_to(value, decoder, reader, receiver):
    """Set every declared IR telemetry counter — across all three declared
    owners — to *value*, without hand-listing the nine counter names."""
    for name in InfraredDecoder.OWNED_TELEMETRY_FIELDS:
        setattr(decoder, name, value)
    for name in PulseReader.OWNED_TELEMETRY_FIELDS:
        setattr(reader, name, value)
    for name in InfraredReceiver.OWNED_TELEMETRY_FIELDS:
        setattr(receiver, name, value)


def test_single_receiver_reset_telemetry_zeroes_every_counter_telemetry_reports():
    """Read/reset symmetry: whatever telemetry() reports, reset_telemetry()
    zeroes — checked generically across every declared counter rather than
    hand-listing them, so a newly added counter is covered automatically."""
    reader = FakePulseReader()
    decoder = TagInfraredDecoder()
    rx = InfraredSingleReceiver(reader, decoder)
    _set_every_owned_counter_to(7, decoder, reader, rx)

    before = rx.telemetry()
    assert all(getattr(before, field) == 7 for field in IrTelemetrySnapshot.FIELDS)

    rx.reset_telemetry()

    after = rx.telemetry()
    assert all(getattr(after, field) == 0 for field in IrTelemetrySnapshot.FIELDS)


def test_multi_receiver_with_one_source_reset_telemetry_zeroes_every_counter_telemetry_reports():
    """The same read/reset symmetry check, run with N=1 — a one-source
    multi-receiver is the same machinery as a single receiver, so the
    guarantee must hold there too."""
    reader = FakePulseReader()
    decoders_built = []

    def decoder_factory():
        decoder = TagInfraredDecoder()
        decoders_built.append(decoder)
        return decoder

    rx = InfraredMultiReceiver([reader], decoder_factory)
    decoder = decoders_built[0]
    _set_every_owned_counter_to(7, decoder, reader, rx)

    before = rx.telemetry()
    assert all(getattr(before, field) == 7 for field in IrTelemetrySnapshot.FIELDS)

    rx.reset_telemetry()

    after = rx.telemetry()
    assert all(getattr(after, field) == 0 for field in IrTelemetrySnapshot.FIELDS)
