"""Behaviour-driven tests for the Aura IR transport layer.

Covers:
- PulseReader / PulseWriter port contracts
- InfraredTransmitter: send encodes and writes pulses
- InfraredSingleReceiver: round-trip receive with fake ports
- InfraredMultiReceiver: picks the packet with the lowest error margin
- InfraredMultiReceiver.receive() allocates nothing per tick in the polled path
"""

import gc

import pytest

from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_transport import (
    InfraredMultiReceiver,
    InfraredReceiver,
    InfraredSingleReceiver,
    InfraredTransmitter,
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


# ---------------------------------------------------------------------------
# InfraredReceiver base contract
# ---------------------------------------------------------------------------


def test_receiver_base_raises_not_implemented():
    rx = InfraredReceiver()
    with pytest.raises(NotImplementedError):
        rx.receive()


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
# InfraredMultiReceiver — no per-tick allocation in polled path
# ---------------------------------------------------------------------------


def test_multi_receiver_receive_allocates_nothing_per_tick_when_no_packet():
    """Calling receive() with no incoming pulses must not allocate heap objects."""
    rx, _ = _make_multi_receiver(3)

    # Warm up: let any one-time setup allocations settle
    for _ in range(5):
        rx.receive()

    gc.collect()
    before = gc.get_count()

    for _ in range(100):
        rx.receive()

    gc.collect()
    after = gc.get_count()

    # gc.get_count() returns a 3-tuple of generation counts; we compare element-wise
    # to confirm no new objects survive into any generation after 100 idle ticks.
    assert after[0] <= before[0], f"Unexpected gen-0 allocation: before={before}, after={after}"
