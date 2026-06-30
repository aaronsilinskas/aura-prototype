"""Tests for _setup_ir's import-probe writer selection.

PIO availability is a property of the silicon: ``_setup_ir`` probes for
``rp2pio`` (present only on RP2040/RP2350) and, when it imports, wires every
emitter with a PIO-backed :class:`PioPulseWriter` driving its own
``rp2pio.StateMachine``. With no ``rp2pio`` (the CPython default) it falls back
to the blocking :class:`PulseOutWriter`. There is no config knob.

This module installs the same CircuitPython hardware stubs as ``test_setup_ir``
and additionally stubs ``rp2pio`` / ``adafruit_pioasm`` so the PIO branch is
exercisable on CPython.
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


class _FakePulseIn:
    """Stub for pulseio.PulseIn."""

    def __init__(self, pin, *, maxlen=256, idle_state=True) -> None:
        self.pin = pin
        self.maxlen = maxlen
        self.idle_state = idle_state
        self._data: list[int] = []

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, index: int) -> int:
        return self._data[index]

    def __delitem__(self, index: int) -> None:
        del self._data[index]


class _FakePulseOut:
    """Stub for pulseio.PulseOut."""

    def __init__(self, pin, *, frequency=38000, duty_cycle=0x8000) -> None:
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = duty_cycle

    def send(self, durations) -> None:
        pass


_pulseio = sys.modules["pulseio"]
_pulseio.PulseIn = _FakePulseIn  # type: ignore[attr-defined]
_pulseio.PulseOut = _FakePulseOut  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# rp2pio / adafruit_pioasm stubs — make the PIO branch importable on CPython.
# ---------------------------------------------------------------------------


class _FakeStateMachine:
    """Recording stub for rp2pio.StateMachine."""

    instances: ClassVar[list[_FakeStateMachine]] = []

    def __init__(self, pin, **kwargs) -> None:
        self.pin = pin
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

from engine.network import AREA_OF_EFFECT, CONE, LINE  # noqa: E402
from hardware.circuitpython.device_builder import _setup_ir  # noqa: E402
from hardware.circuitpython.infrared_io import PulseOutWriter  # noqa: E402
from hardware.circuitpython.pio_pulse_writer import PioPulseWriter  # noqa: E402

_RX_PIN = object()
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


def test_setup_ir_uses_pulse_out_writer_when_rp2pio_absent():
    """Without rp2pio (the CPython default) every transmitter wraps PulseOutWriter."""
    transmitters, _receiver = _setup_ir(_RX_PIN, _LINE_PIN, cone_pin=_CONE_PIN, aoe_pin=_AOE_PIN)
    for emitter in (LINE, CONE, AREA_OF_EFFECT):
        assert isinstance(transmitters[emitter]._writer, PulseOutWriter)


# ---------------------------------------------------------------------------
# PIO selection: rp2pio present → PioPulseWriter per emitter
# ---------------------------------------------------------------------------


def test_setup_ir_uses_pio_writer_when_rp2pio_present(with_rp2pio):
    """With rp2pio importable, the LINE transmitter wraps a PioPulseWriter."""
    transmitters, _receiver = _setup_ir(_RX_PIN, _LINE_PIN)
    assert isinstance(transmitters[LINE]._writer, PioPulseWriter)


def test_setup_ir_builds_one_state_machine_per_wired_emitter(with_rp2pio):
    """One StateMachine is built per wired emitter, unconditionally."""
    _setup_ir(_RX_PIN, _LINE_PIN, cone_pin=_CONE_PIN, aoe_pin=_AOE_PIN)
    assert len(_FakeStateMachine.instances) == 3


def test_setup_ir_pio_writers_share_the_gate_with_receiver(with_rp2pio):
    """The shared IrTransmitGate is injected into the receiver and every PIO transmitter."""
    transmitters, receiver = _setup_ir(_RX_PIN, _LINE_PIN, cone_pin=_CONE_PIN, aoe_pin=_AOE_PIN)
    gate = receiver._gate
    assert gate is not None
    for emitter in (LINE, CONE, AREA_OF_EFFECT):
        assert transmitters[emitter]._gate is gate


def test_setup_ir_pio_transmitter_send_returns_before_completion(with_rp2pio):
    """A PIO-wired transmitter's send starts the write and returns while still busy."""
    transmitters, _receiver = _setup_ir(_RX_PIN, _LINE_PIN)
    transmitter = transmitters[LINE]
    transmitter.send(b"\x01\x02")
    assert transmitter._writer.is_busy() is True
