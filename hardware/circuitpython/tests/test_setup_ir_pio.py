"""Tests for _make_writer's import-probe writer selection.

PIO availability is a property of the silicon: ``_make_writer`` probes for
``rp2pio`` (present only on RP2040/RP2350) and, when it imports, returns a
PIO-backed :class:`PioPulseWriter` driving its own ``rp2pio.StateMachine``.
With no ``rp2pio`` (the CPython default) it falls back to the blocking
:class:`PulseOutWriter`. There is no config knob.

This module installs the same CircuitPython hardware stubs as ``test_setup_ir``
and additionally stubs ``rp2pio`` / ``adafruit_pioasm`` so the PIO branch is
exercisable on CPython. Tests call ``_make_writer(pin)`` directly — selection
is exercised in isolation, not routed through ``_setup_ir``'s assembly.
"""

from __future__ import annotations

import sys
import types
from typing import ClassVar

# ---------------------------------------------------------------------------
# Baseline CircuitPython hardware stubs (mirrors test_setup_ir).
# ---------------------------------------------------------------------------

for _name in (
    "adafruit_is31fl3741",
    "adafruit_is31fl3741.adafruit_rgbmatrixqt",
    "board",
    "busio",
    "digitalio",
    "pulseio",
):
    sys.modules.setdefault(_name, types.ModuleType(_name))

_is31 = sys.modules["adafruit_is31fl3741"]
if not hasattr(_is31, "MUST_BUFFER"):
    _is31.MUST_BUFFER = 0  # type: ignore[attr-defined]

_rgbqt = sys.modules["adafruit_is31fl3741.adafruit_rgbmatrixqt"]
if not hasattr(_rgbqt, "Adafruit_RGBMatrixQT"):
    _rgbqt.Adafruit_RGBMatrixQT = type("Adafruit_RGBMatrixQT", (), {})  # type: ignore[attr-defined]

_digitalio = sys.modules["digitalio"]
if not hasattr(_digitalio, "DigitalInOut"):
    _digitalio.DigitalInOut = type(  # type: ignore[attr-defined]
        "DigitalInOut",
        (),
        {
            "__init__": lambda self, pin: None,
            "switch_to_input": lambda self, **kw: None,
            "switch_to_output": lambda self, **kw: None,
            "value": True,
        },
    )
if not hasattr(_digitalio, "Pull"):
    _digitalio.Pull = types.SimpleNamespace(UP=0, DOWN=1)  # type: ignore[attr-defined]

_busio = sys.modules["busio"]
if not hasattr(_busio, "I2C"):
    _busio.I2C = type("I2C", (), {"__init__": lambda self, *a: None})  # type: ignore[attr-defined]


class _FakePulseOut:
    """Stub for pulseio.PulseOut."""

    def __init__(self, pin, *, frequency=38000, duty_cycle=0x8000) -> None:
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = duty_cycle

    def send(self, durations) -> None:
        pass


_pulseio = sys.modules["pulseio"]
_pulseio.PulseOut = _FakePulseOut  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# rp2pio / adafruit_pioasm stubs — make the PIO branch importable on CPython.
# ---------------------------------------------------------------------------


class _FakeStateMachine:
    """Recording stub for rp2pio.StateMachine."""

    instances: ClassVar[list[_FakeStateMachine]] = []

    def __init__(self, program, frequency, /, *, first_set_pin=None, **kwargs) -> None:
        # Mirror the real rp2pio.StateMachine signature: program and frequency
        # are positional-only, the transmit pin arrives as first_set_pin. A
        # regression that passes program=/frequency= by keyword fails here.
        self.program = program
        self.frequency = frequency
        self.pin = first_set_pin
        self.kwargs = kwargs
        self.writing = False
        _FakeStateMachine.instances.append(self)

    def background_write(self, buffer) -> None:
        self.writing = True


class _FakeProgram:
    """Stub for adafruit_pioasm.Program."""

    def __init__(self, source, **kwargs) -> None:
        self.source = source
        self.assembled = source


import pytest  # noqa: E402

from hardware.circuitpython.device_builder import _make_writer  # noqa: E402
from hardware.circuitpython.infrared_io import PulseOutWriter  # noqa: E402
from hardware.circuitpython.pio_pulse_writer import PioPulseWriter  # noqa: E402
from hardware.shared.ir_protocol import AuraInfraredEncoder  # noqa: E402
from hardware.shared.ir_transport import InfraredTransmitter  # noqa: E402

_LINE_PIN = object()
_CONE_PIN = object()
_AOE_PIN = object()


@pytest.fixture
def with_rp2pio():
    """Install rp2pio + adafruit_pioasm stubs for the duration of a test."""
    _FakeStateMachine.instances.clear()
    rp2pio = types.ModuleType("rp2pio")
    rp2pio.StateMachine = _FakeStateMachine  # type: ignore[attr-defined]
    pioasm = types.ModuleType("adafruit_pioasm")
    pioasm.Program = _FakeProgram  # type: ignore[attr-defined]
    sys.modules["rp2pio"] = rp2pio
    sys.modules["adafruit_pioasm"] = pioasm
    try:
        yield
    finally:
        sys.modules.pop("rp2pio", None)
        sys.modules.pop("adafruit_pioasm", None)


@pytest.fixture(autouse=True)
def without_rp2pio_by_default():
    """Ensure no leftover rp2pio stub leaks into the fallback tests."""
    sys.modules.pop("rp2pio", None)
    sys.modules.pop("adafruit_pioasm", None)
    yield


# ---------------------------------------------------------------------------
# Fallback: no rp2pio → blocking PulseOutWriter
# ---------------------------------------------------------------------------


def test_make_writer_returns_pulse_out_writer_when_rp2pio_absent():
    """Without rp2pio (the CPython default) _make_writer returns a PulseOutWriter."""
    for pin in (_LINE_PIN, _CONE_PIN, _AOE_PIN):
        writer, _kind = _make_writer(pin)
        assert isinstance(writer, PulseOutWriter)


def test_make_writer_reports_pulseio_kind_when_rp2pio_absent():
    """Without rp2pio, the reported kind is "pulseio" -- what build_hardware's
    ir narration logs as writer=pulseio (#763)."""
    _writer, kind = _make_writer(_LINE_PIN)
    assert kind == "pulseio"


def test_make_writer_pulse_out_uses_38khz_carrier():
    """The PulseOut backing the fallback writer is configured at 38 kHz carrier."""
    writer, _kind = _make_writer(_LINE_PIN)
    assert writer._pulseout.frequency == 38000


def test_make_writer_wires_pulse_out_to_the_given_pin():
    """The fallback writer's PulseOut is opened on the pin passed to _make_writer."""
    writer, _kind = _make_writer(_LINE_PIN)
    assert writer._pulseout.pin is _LINE_PIN


# ---------------------------------------------------------------------------
# PIO selection: rp2pio present → PioPulseWriter per emitter
# ---------------------------------------------------------------------------


def test_make_writer_returns_pio_writer_when_rp2pio_present(with_rp2pio):
    """With rp2pio importable, _make_writer returns a PioPulseWriter."""
    writer, _kind = _make_writer(_LINE_PIN)
    assert isinstance(writer, PioPulseWriter)


def test_make_writer_reports_pio_kind_when_rp2pio_present(with_rp2pio):
    """With rp2pio importable, the reported kind is "pio" -- what
    build_hardware's ir narration logs as writer=pio (#763)."""
    _writer, kind = _make_writer(_LINE_PIN)
    assert kind == "pio"


def test_make_writer_builds_one_state_machine_per_call(with_rp2pio):
    """Each _make_writer call builds its own StateMachine, unconditionally."""
    for pin in (_LINE_PIN, _CONE_PIN, _AOE_PIN):
        _make_writer(pin)
    assert len(_FakeStateMachine.instances) == 3


def test_make_writer_pio_transmitter_send_returns_before_completion(with_rp2pio):
    """A PIO-wired transmitter's send starts the write and returns while still busy."""
    writer, _kind = _make_writer(_LINE_PIN)
    transmitter = InfraredTransmitter(writer, AuraInfraredEncoder())
    transmitter.send(b"\x01\x02")
    assert transmitter._writer.is_busy() is True
