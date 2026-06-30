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

from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder
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
    """Recording fake — stores every write_pulses call for assertions."""

    def __init__(self):
        self.calls = []

    def write_pulses(self, durations) -> None:
        self.calls.append(list(durations))


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


def test_gate_consume_flush_is_false_before_any_emission():
    gate = IrTransmitGate()
    assert gate.consume_flush() is False


def test_gate_consume_flush_is_true_once_after_end_transmit():
    gate = IrTransmitGate()
    gate.begin_transmit()
    gate.end_transmit()

    assert gate.consume_flush() is True
    assert gate.consume_flush() is False


def test_gate_consume_flush_is_not_armed_while_still_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    assert gate.consume_flush() is False


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
    assert gate.consume_flush() is True


def test_transmitter_with_gate_releases_gate_even_when_writer_raises():
    class RaisingWriter(PulseWriter):
        def write_pulses(self, durations) -> None:
            raise RuntimeError("hardware fault")

    gate = IrTransmitGate()
    tx = InfraredTransmitter(RaisingWriter(), AuraInfraredEncoder(), gate)

    with pytest.raises(RuntimeError):
        tx.send(b"\x01")

    assert gate.transmitting is False
    assert gate.consume_flush() is True


# ---------------------------------------------------------------------------
# InfraredReceiver base contract
# ---------------------------------------------------------------------------


def test_receiver_base_raises_not_implemented():
    rx = InfraredReceiver()
    with pytest.raises(NotImplementedError):
        rx.receive()


def test_receiver_base_defaults_all_telemetry_counters_to_zero():
    rx = InfraredReceiver()

    assert rx.pulses_seen == 0
    assert rx.packets_surfaced == 0
    assert rx.packets_started == 0
    assert rx.packets_completed == 0
    assert rx.preamble_reject == 0
    assert rx.mark_reject == 0
    assert rx.space_reject == 0
    assert rx.buffer_full_on_poll == 0
    assert rx.pulses_dropped_transmitting == 0


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

    assert rx.pulses_seen == len(pulses)


def test_single_receiver_pulses_seen_accumulates_across_receive_calls():
    reader = FakePulseReader()
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    reader.load([100, 200])
    rx.receive()
    reader.load([300])
    rx.receive()

    assert rx.pulses_seen == 3


def test_single_receiver_packets_surfaced_increments_on_successful_receive():
    payload = b"\x01"
    reader = FakePulseReader(_encode_pulses(payload))
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    rx.receive()
    rx.receive()  # second call: no more pulses, no new packet

    assert rx.packets_surfaced == 1


def test_single_receiver_delegates_decoder_counters_from_tag_decoder():
    """The whole path reads off ir_receiver — decoder counters surface here."""
    decoder = TagInfraredDecoder()
    bad_preamble = list(TAG_PREAMBLE)
    bad_preamble[1] = 4000  # invalid but below the inter-frame gap threshold
    reader = FakePulseReader(bad_preamble)
    rx = InfraredSingleReceiver(reader, decoder)

    rx.receive()

    assert rx.preamble_reject == decoder.preamble_reject == 1
    assert rx.packets_started == decoder.packets_started == 0
    assert rx.packets_completed == decoder.packets_completed == 0
    assert rx.mark_reject == decoder.mark_reject == 0
    assert rx.space_reject == decoder.space_reject == 0


def test_single_receiver_delegates_buffer_full_on_poll_from_reader():
    reader = FakePulseReader()
    reader.buffer_full_on_poll = 3
    rx = InfraredSingleReceiver(reader, AuraInfraredDecoder())

    assert rx.buffer_full_on_poll == 3


def test_single_receiver_reset_telemetry_zeroes_whole_ir_path():
    decoder = TagInfraredDecoder()
    payload = [*list(TagInfraredEncoder().encode(bytearray([0x10]))), TAG_PREAMBLE[0]]
    reader = FakePulseReader(payload)
    rx = InfraredSingleReceiver(reader, decoder)
    reader.buffer_full_on_poll = 2
    rx.receive()

    rx.reset_telemetry()

    assert rx.pulses_seen == 0
    assert rx.packets_surfaced == 0
    assert rx.packets_started == 0
    assert rx.packets_completed == 0
    assert rx.preamble_reject == 0
    assert rx.mark_reject == 0
    assert rx.space_reject == 0
    assert rx.buffer_full_on_poll == 0
    assert decoder.packets_started == 0
    assert decoder.packets_completed == 0
    assert reader.buffer_full_on_poll == 0


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

    assert rx.pulses_dropped_transmitting == len(pulses)
    assert rx.pulses_seen == 0


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
    assert rx.pulses_dropped_transmitting == 2

    # Next poll: gate is fully idle, a genuine packet decodes normally.
    payload = b"\x07"
    reader.load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


def test_single_receiver_gate_idle_does_not_consume_flush_repeatedly():
    """consume_flush() is one-shot — a second idle poll must not re-drop."""
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
    assert rx.pulses_dropped_transmitting == 2

    rx.reset_telemetry()

    assert rx.pulses_dropped_transmitting == 0


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

    assert rx.pulses_dropped_transmitting == 5
    assert rx.pulses_seen == 0


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
    assert rx.pulses_dropped_transmitting == 1

    payload = b"\x21"
    readers[1].load(_encode_pulses(payload))
    assert rx.receive() == bytearray(payload)


def test_multi_receiver_reset_telemetry_zeroes_pulses_dropped_transmitting():
    gate = IrTransmitGate()
    gate.begin_transmit()
    rx, readers = _make_gated_multi_receiver(2, gate)
    readers[0].load([100])

    rx.receive()
    assert rx.pulses_dropped_transmitting == 1

    rx.reset_telemetry()

    assert rx.pulses_dropped_transmitting == 0


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
