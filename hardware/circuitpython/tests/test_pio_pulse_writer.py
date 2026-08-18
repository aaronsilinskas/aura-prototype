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
from hardware.circuitpython.pio_pulse_writer import (  # noqa: E402
    _CARRIER_PERIOD_US,
    _INTERFRAME_GAP_US,
    PioPulseWriter,
    _duration_us_to_loops,
)
from hardware.shared.ir_codecs.aura import (  # noqa: E402
    IR_HEADER_MARK,
    IR_LEAD_OUT,
    IR_UNIT,
)


def _make_writer():
    sm = _FakeStateMachine(_FakeProgram("nop"), 1, first_set_pin=object())
    return PioPulseWriter(sm), sm


def _loops_to_us(loops: int) -> int:
    """Reconstruct the on-wire duration a stored loop count actually produces.

    The program runs the loop body ``loops + 1`` times, each spanning
    ``_CARRIER_PERIOD_US`` µs — the inverse of _duration_us_to_loops, used to
    assert the round-trip stays within the protocol's timing tolerance.
    """
    return (loops + 1) * _CARRIER_PERIOD_US


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


def test_is_busy_is_false_before_any_write_even_when_state_machine_reports_writing():
    """A fresh SM whose ``writing`` reads True must not report busy pre-write.

    ``rp2pio`` leaves the field behind ``writing`` uninitialised until the first
    ``background_write``, so real hardware can report ``writing == True`` on a
    brand-new state machine. If the writer trusted that, the "send only when
    idle" caller would deadlock — never sending, so never clearing the flag.
    """
    sm = _FakeStateMachine(_FakeProgram("nop"), 1, first_set_pin=object())
    sm.writing = True  # uninitialised-hardware flag, before any write_pulses
    writer = PioPulseWriter(sm)
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


def test_write_pulses_hands_the_built_buffer_to_the_dma():
    """The exact buffer handed to background_write is the writer's in-flight one.

    The writer builds its own even-length DMA buffer (converted + padded), so
    the contract is that the buffer given to the DMA is the one it retains — not
    that it reuses the caller's array.
    """
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200, 300]))
    assert sm.background_writes[0] is writer._inflight


def test_in_flight_buffer_is_held_until_write_completes():
    """The DMA buffer is kept referenced while the write is outstanding."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200, 300]))
    assert writer._inflight is sm.background_writes[0]  # ownership is the contract


def test_in_flight_buffer_reference_is_dropped_once_idle():
    """Once is_busy() reads False, the writer releases the in-flight buffer."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200]))
    sm.writing = False
    assert writer.is_busy() is False
    assert writer._inflight is None


def test_busy_query_keeps_buffer_while_still_writing():
    """Polling is_busy() mid-write does not prematurely drop the buffer."""
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [100, 200]))
    assert writer.is_busy() is True
    assert writer._inflight is sm.background_writes[0]


# ---------------------------------------------------------------------------
# µs → carrier-period loop-count conversion
# ---------------------------------------------------------------------------


def test_write_pulses_converts_us_durations_to_loop_counts():
    """write_pulses hands the DMA carrier-period counts, not raw µs.

    The raw encoder values are microseconds; the DMA must receive carrier-period
    counts, not the µs values fed straight through (the original defect). A
    single (odd-length) input is padded with the gap, so the converted duration
    is the buffer's first element.
    """
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [IR_UNIT]))
    assert sm.background_writes[0][0] == _duration_us_to_loops(IR_UNIT)


def test_write_pulses_pads_odd_frames_to_even_with_a_trailing_gap():
    """An odd-length frame is padded to even with the inter-frame gap appended.

    Even length keeps the PIO program's pull-mark/pull-space phase aligned across
    frames; an odd count would clock the next frame's header mark out as a space.
    """
    writer, sm = _make_writer()
    writer.write_pulses(array("H", [IR_UNIT, IR_UNIT, IR_LEAD_OUT]))  # odd (3)
    buffer = sm.background_writes[0]
    assert len(buffer) == 4  # padded to even
    assert buffer[-1] == _duration_us_to_loops(_INTERFRAME_GAP_US)


def test_header_mark_round_trips_within_protocol_tolerance():
    """A 4000 µs header mark reconstructs to ~4000 µs, well inside ±250 µs."""
    reconstructed = _loops_to_us(_duration_us_to_loops(IR_HEADER_MARK))
    assert abs(reconstructed - IR_HEADER_MARK) <= IR_UNIT // 2


def test_base_unit_round_trips_within_protocol_tolerance():
    """The 500 µs base unit — the shortest real duration — stays within ±250 µs."""
    reconstructed = _loops_to_us(_duration_us_to_loops(IR_UNIT))
    assert abs(reconstructed - IR_UNIT) <= IR_UNIT // 2


def test_lead_out_round_trips_within_protocol_tolerance():
    """The 5000 µs lead-out — the longest duration — stays within ±250 µs."""
    reconstructed = _loops_to_us(_duration_us_to_loops(IR_LEAD_OUT))
    assert abs(reconstructed - IR_LEAD_OUT) <= IR_UNIT // 2


def test_shortest_duration_never_yields_a_negative_loop_count():
    """A sub-period duration floors to a single iteration, not a negative count.

    A stored -1 would wrap to a ~65535-iteration loop on the 16-bit register,
    hanging the transmit — the failure mode the floor guards against.
    """
    assert _duration_us_to_loops(1) == 0
