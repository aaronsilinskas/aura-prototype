"""Tests for PulseInReader and PulseOutWriter — CircuitPython pulseio adapters."""

from array import array
from typing import TYPE_CHECKING, cast

from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter

if TYPE_CHECKING:
    import pulseio

# ---------------------------------------------------------------------------
# Fake pulseio hardware stubs
# ---------------------------------------------------------------------------


class FakePulseIn:
    """Minimal stub for pulseio.PulseIn.

    ``maxlen`` mirrors the real ``pulseio.PulseIn`` attribute the reader
    polls to detect buffer overrun.
    """

    def __init__(self, pulses=None, maxlen=256) -> None:
        self._pulses: list[int] = list(pulses) if pulses else []
        self.maxlen = maxlen

    def __len__(self) -> int:
        return len(self._pulses)

    def popleft(self) -> int:
        return self._pulses.pop(0)

    def clear(self) -> None:
        self._pulses.clear()


def fake_pulse_in(pulses: list[int] | None = None, maxlen: int = 256) -> "pulseio.PulseIn":
    return cast("pulseio.PulseIn", FakePulseIn(pulses, maxlen))


class FakePulseOut:
    """Recording stub for pulseio.PulseOut."""

    def __init__(self) -> None:
        self.send_calls: list = []

    def send(self, pulses) -> None:
        self.send_calls.append(pulses)


def as_pulse_out(pulseout: FakePulseOut) -> "pulseio.PulseOut":
    return cast("pulseio.PulseOut", pulseout)


# ---------------------------------------------------------------------------
# PulseInReader — wraps pulseio.PulseIn
# ---------------------------------------------------------------------------


def test_pulse_in_reader_returns_none_when_buffer_empty():
    reader = PulseInReader(fake_pulse_in())
    assert reader.read_pulse() is None


def test_pulse_in_reader_returns_first_pulse_when_available():
    reader = PulseInReader(fake_pulse_in([1234]))
    assert reader.read_pulse() == 1234


def test_pulse_in_reader_advances_to_next_pulse_after_reading():
    reader = PulseInReader(fake_pulse_in([500, 1000]))

    reader.read_pulse()

    assert reader.read_pulse() == 1000


def test_pulse_in_reader_returns_pulses_in_order():
    reader = PulseInReader(fake_pulse_in([100, 200, 300]))
    assert reader.read_pulse() == 100
    assert reader.read_pulse() == 200
    assert reader.read_pulse() == 300


def test_pulse_in_reader_returns_none_after_buffer_drained():
    reader = PulseInReader(fake_pulse_in([500]))
    reader.read_pulse()
    assert reader.read_pulse() is None


# ---------------------------------------------------------------------------
# PulseInReader — buffer_full_on_poll telemetry
# ---------------------------------------------------------------------------


def test_buffer_full_on_poll_increments_when_buffer_at_maxlen_on_read():
    reader = PulseInReader(fake_pulse_in([500, 1000], maxlen=2))

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 1


def test_buffer_full_on_poll_does_not_increment_when_buffer_below_maxlen():
    reader = PulseInReader(fake_pulse_in([500], maxlen=2))

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 0


def test_buffer_full_on_poll_does_not_increment_when_buffer_empty():
    reader = PulseInReader(fake_pulse_in(maxlen=2))

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 0


def test_buffer_full_on_poll_counts_once_per_full_read_not_per_drain():
    """Only the read that observes maxlen counts; later reads of the same
    drain see a shorter buffer and do not increment further."""
    reader = PulseInReader(fake_pulse_in([500, 1000], maxlen=2))

    reader.read_pulse()  # buffer was at maxlen (2) -> counts
    reader.read_pulse()  # buffer now has 1 entry -> does not count

    assert reader.buffer_full_on_poll == 1


def test_reset_telemetry_zeroes_buffer_full_on_poll():
    reader = PulseInReader(fake_pulse_in([500, 1000], maxlen=2))
    reader.read_pulse()
    assert reader.buffer_full_on_poll == 1

    reader.reset_telemetry()

    assert reader.buffer_full_on_poll == 0


# ---------------------------------------------------------------------------
# PulseOutWriter — wraps pulseio.PulseOut
# ---------------------------------------------------------------------------


def test_pulse_out_writer_sends_pulses_via_pulseout():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(as_pulse_out(pulseout))
    pulses = array("H", [500, 1500, 500, 500])
    writer.write_pulses(pulses)
    assert len(pulseout.send_calls) == 1
    assert pulseout.send_calls[0] == pulses


def test_pulse_out_writer_sends_each_call_separately():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(as_pulse_out(pulseout))
    writer.write_pulses(array("H", [100]))
    writer.write_pulses(array("H", [200]))
    assert len(pulseout.send_calls) == 2


# ---------------------------------------------------------------------------
# PulseOutWriter — is_busy reports across a (faked) blocking send
# ---------------------------------------------------------------------------


def test_pulse_out_writer_is_busy_false_before_any_send():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(as_pulse_out(pulseout))
    assert writer.is_busy() is False


def test_pulse_out_writer_is_busy_false_after_send_completes():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(as_pulse_out(pulseout))
    writer.write_pulses(array("H", [500]))
    assert writer.is_busy() is False
