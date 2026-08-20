"""Tests for PulseInReader and PulseOutWriter — CircuitPython pulseio adapters."""

from __future__ import annotations

from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter

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


class FakePulseOut:
    """Recording stub for pulseio.PulseOut."""

    def __init__(self) -> None:
        self.send_calls: list = []

    def send(self, pulses) -> None:
        self.send_calls.append(pulses)


# ---------------------------------------------------------------------------
# PulseInReader — wraps pulseio.PulseIn
# ---------------------------------------------------------------------------


def test_pulse_in_reader_returns_none_when_buffer_empty():
    pulsein = FakePulseIn()
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() is None


def test_pulse_in_reader_returns_first_pulse_when_available():
    pulsein = FakePulseIn([1234])
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() == 1234


def test_pulse_in_reader_advances_to_next_pulse_after_reading():
    pulsein = FakePulseIn([500, 1000])
    reader = PulseInReader(pulsein)

    reader.read_pulse()

    assert reader.read_pulse() == 1000


def test_pulse_in_reader_returns_pulses_in_order():
    pulsein = FakePulseIn([100, 200, 300])
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() == 100
    assert reader.read_pulse() == 200
    assert reader.read_pulse() == 300


def test_pulse_in_reader_returns_none_after_buffer_drained():
    pulsein = FakePulseIn([500])
    reader = PulseInReader(pulsein)
    reader.read_pulse()
    assert reader.read_pulse() is None


# ---------------------------------------------------------------------------
# PulseInReader — buffer_full_on_poll telemetry
# ---------------------------------------------------------------------------


def test_buffer_full_on_poll_increments_when_buffer_at_maxlen_on_read():
    pulsein = FakePulseIn([500, 1000], maxlen=2)
    reader = PulseInReader(pulsein)

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 1


def test_buffer_full_on_poll_does_not_increment_when_buffer_below_maxlen():
    pulsein = FakePulseIn([500], maxlen=2)
    reader = PulseInReader(pulsein)

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 0


def test_buffer_full_on_poll_does_not_increment_when_buffer_empty():
    pulsein = FakePulseIn(maxlen=2)
    reader = PulseInReader(pulsein)

    reader.read_pulse()

    assert reader.buffer_full_on_poll == 0


def test_buffer_full_on_poll_counts_once_per_full_read_not_per_drain():
    """Only the read that observes maxlen counts; later reads of the same
    drain see a shorter buffer and do not increment further."""
    pulsein = FakePulseIn([500, 1000], maxlen=2)
    reader = PulseInReader(pulsein)

    reader.read_pulse()  # buffer was at maxlen (2) -> counts
    reader.read_pulse()  # buffer now has 1 entry -> does not count

    assert reader.buffer_full_on_poll == 1


def test_reset_telemetry_zeroes_buffer_full_on_poll():
    pulsein = FakePulseIn([500, 1000], maxlen=2)
    reader = PulseInReader(pulsein)
    reader.read_pulse()
    assert reader.buffer_full_on_poll == 1

    reader.reset_telemetry()

    assert reader.buffer_full_on_poll == 0


# ---------------------------------------------------------------------------
# PulseOutWriter — wraps pulseio.PulseOut
# ---------------------------------------------------------------------------


def test_pulse_out_writer_sends_pulses_via_pulseout():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    pulses = [500, 1500, 500, 500]
    writer.write_pulses(pulses)
    assert len(pulseout.send_calls) == 1
    assert pulseout.send_calls[0] is pulses


def test_pulse_out_writer_sends_each_call_separately():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    writer.write_pulses([100])
    writer.write_pulses([200])
    assert len(pulseout.send_calls) == 2


# ---------------------------------------------------------------------------
# PulseOutWriter — is_busy reports across a (faked) blocking send
# ---------------------------------------------------------------------------


def test_pulse_out_writer_is_busy_false_before_any_send():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    assert writer.is_busy() is False


def test_pulse_out_writer_is_busy_true_during_blocking_send():
    """The blocking send call observes is_busy() True from inside pulseout.send."""

    class ObservingPulseOut(FakePulseOut):
        def __init__(self, writer_ref) -> None:
            super().__init__()
            self._writer_ref = writer_ref
            self.was_busy_during_send = None

        def send(self, pulses) -> None:
            super().send(pulses)
            self.was_busy_during_send = self._writer_ref[0].is_busy()

    writer_ref = [None]
    pulseout = ObservingPulseOut(writer_ref)
    writer = PulseOutWriter(pulseout)
    writer_ref[0] = writer

    writer.write_pulses([500, 1500])

    assert pulseout.was_busy_during_send is True


def test_pulse_out_writer_is_busy_false_after_send_completes():
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    writer.write_pulses([500])
    assert writer.is_busy() is False
