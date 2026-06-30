"""Tests for PioPulseWriter — the RP2040/RP2350 PIO-backed IR PulseWriter.

The PIO branch never runs on CPython (real hardware has ``rp2pio``; CPython
does not). The adapter's module import is hardware-guarded, so these tests
drive a fake ``rp2pio.StateMachine`` directly — without any hardware library —
and assert the adapter's externally observable contract:

- ``write_pulses`` starts a non-blocking ``background_write`` and returns at once
- the in-flight pulse buffer is held referenced until the write completes
- ``is_busy()`` reflects the state machine's ``writing`` flag
- the reference is dropped once ``is_busy()`` next reads ``False``

The carrier (38 kHz) is generated inside the PIO program, so the writer feeds
the state machine raw mark/space durations only.
"""

from __future__ import annotations

from array import array

# ---------------------------------------------------------------------------
# Stub rp2pio + adafruit_pioasm before importing the adapter under test.
# ---------------------------------------------------------------------------


class _FakeStateMachine:
    """Recording stub for ``rp2pio.StateMachine``.

    ``writing`` is a plain attribute the test drives to simulate the DMA
    background write finishing. ``background_write`` records the buffer it was
    handed and flips ``writing`` True; the test clears ``writing`` to model
    completion.
    """

    def __init__(self, program, frequency, /, *, first_set_pin=None, **kwargs) -> None:
        # Mirrors the real rp2pio.StateMachine signature (see make_state_machine):
        # program and frequency are positional-only, the pin is first_set_pin.
        self.program = program
        self.frequency = frequency
        self.pin = first_set_pin
        self.kwargs = kwargs
        self.background_writes: list = []
        self.writing = False

    def background_write(self, buffer) -> None:
        self.background_writes.append(buffer)
        self.writing = True


class _FakeProgram:
    """Stub for an assembled ``adafruit_pioasm.Program``."""

    def __init__(self, source: str, **kwargs) -> None:
        self.source = source
        self.kwargs = kwargs


# The adapter's module import is hardware-guarded (rp2pio is imported lazily,
# only inside make_state_machine), so importing PioPulseWriter here needs no
# rp2pio stub and leaks nothing into sys.modules. The tests drive a fake state
# machine directly, exercising the writer without the hardware libraries.
from hardware.circuitpython.pio_pulse_writer import PioPulseWriter  # noqa: E402


def _make_writer():
    sm = _FakeStateMachine(_FakeProgram("nop"), 1, first_set_pin=object())
    return PioPulseWriter(sm), sm


# ---------------------------------------------------------------------------
# write_pulses — non-blocking start
# ---------------------------------------------------------------------------


def test_write_pulses_starts_a_background_write():
    """write_pulses kicks off a DMA-fed background_write on the state machine."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200, 300]))
    assert len(sm.background_writes) == 1


def test_write_pulses_returns_before_transmission_completes():
    """write_pulses returns while the send is still outstanding (non-blocking)."""
    writer, _sm = _make_writer()
    writer.write_pulses(array("H", [100, 200]))
    assert writer.is_busy() is True


# ---------------------------------------------------------------------------
# is_busy — reflects the state machine's writing flag
# ---------------------------------------------------------------------------


def test_is_busy_is_false_before_any_write():
    """A freshly constructed writer reports idle."""
    writer, _sm = _make_writer()
    assert writer.is_busy() is False


def test_is_busy_reflects_state_machine_writing_flag():
    """is_busy mirrors the state machine's writing state as the DMA completes."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200]))
    assert writer.is_busy() is True
    sm.writing = False
    assert writer.is_busy() is False


# ---------------------------------------------------------------------------
# Buffer ownership — held for the DMA lifetime, dropped when idle
# ---------------------------------------------------------------------------


def test_write_pulses_hands_the_same_buffer_to_the_dma():
    """The exact pulse array is handed to background_write — not a copy."""
    writer, sm = _make_writer()
    buffer = array("H", [100, 200, 300])
    writer.write_pulses(buffer)
    assert sm.background_writes[0] is buffer


def test_in_flight_buffer_is_held_until_write_completes():
    """The pulse buffer is kept referenced while the write is outstanding."""
    writer, _sm = _make_writer()
    buffer = array("H", [100, 200, 300])
    writer.write_pulses(buffer)
    assert writer._inflight is buffer  # buffer ownership is the adapter's contract


def test_in_flight_buffer_reference_is_dropped_once_idle():
    """Once is_busy() reads False, the writer releases the in-flight buffer."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200]))
    sm.writing = False
    assert writer.is_busy() is False
    assert writer._inflight is None


def test_busy_query_keeps_buffer_while_still_writing():
    """Polling is_busy() mid-write does not prematurely drop the buffer."""
    writer, _sm = _make_writer()
    buffer = array("H", [100, 200])
    writer.write_pulses(buffer)
    assert writer.is_busy() is True
    assert writer._inflight is buffer
