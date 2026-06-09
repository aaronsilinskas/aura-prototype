"""Tests for PulseInReader and PulseOutWriter — CircuitPython pulseio adapters.

Covers:
- PulseInReader.read_pulse returns pulses from the pulsein buffer in order
- PulseInReader.read_pulse returns None when the buffer is empty
- PulseInReader.read_pulse clears the pulsein buffer entry after reading
- PulseOutWriter.write_pulses sends the pulse array via pulseio.PulseOut
"""

from __future__ import annotations

from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter

# ---------------------------------------------------------------------------
# Fake pulseio hardware stubs
# ---------------------------------------------------------------------------


class FakePulseIn:
    """Minimal stub for pulseio.PulseIn.

    Backed by a list; index access returns the value, del removes it,
    len returns the current count, and clear empties the list.
    """

    def __init__(self, pulses=None) -> None:
        self._pulses: list[int] = list(pulses) if pulses else []

    def __len__(self) -> int:
        return len(self._pulses)

    def __getitem__(self, index: int) -> int:
        return self._pulses[index]

    def __delitem__(self, index: int) -> None:
        del self._pulses[index]

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
    """read_pulse returns None immediately when no pulses are buffered."""
    pulsein = FakePulseIn()
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() is None


def test_pulse_in_reader_returns_first_pulse_when_available():
    """read_pulse returns the first buffered pulse duration."""
    pulsein = FakePulseIn([1234])
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() == 1234


def test_pulse_in_reader_advances_to_next_pulse_after_reading():
    """Consuming one pulse leaves the next pulse available on the following read."""
    pulsein = FakePulseIn([500, 1000])
    reader = PulseInReader(pulsein)

    reader.read_pulse()

    assert reader.read_pulse() == 1000


def test_pulse_in_reader_returns_pulses_in_order():
    """read_pulse drains pulses in the order they were buffered."""
    pulsein = FakePulseIn([100, 200, 300])
    reader = PulseInReader(pulsein)
    assert reader.read_pulse() == 100
    assert reader.read_pulse() == 200
    assert reader.read_pulse() == 300


def test_pulse_in_reader_returns_none_after_buffer_drained():
    """read_pulse returns None once all buffered pulses have been consumed."""
    pulsein = FakePulseIn([500])
    reader = PulseInReader(pulsein)
    reader.read_pulse()
    assert reader.read_pulse() is None


# ---------------------------------------------------------------------------
# PulseOutWriter — wraps pulseio.PulseOut
# ---------------------------------------------------------------------------


def test_pulse_out_writer_sends_pulses_via_pulseout():
    """write_pulses forwards the pulse array to pulseout.send."""
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    pulses = [500, 1500, 500, 500]
    writer.write_pulses(pulses)
    assert len(pulseout.send_calls) == 1
    assert pulseout.send_calls[0] is pulses


def test_pulse_out_writer_sends_each_call_separately():
    """Each write_pulses call results in exactly one pulseout.send call."""
    pulseout = FakePulseOut()
    writer = PulseOutWriter(pulseout)
    writer.write_pulses([100])
    writer.write_pulses([200])
    assert len(pulseout.send_calls) == 2
