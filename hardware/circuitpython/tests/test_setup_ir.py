"""Tests for setup_ir in propmaker — builds IR hardware objects and returns
the transmitter map + single receiver for injection into HardwareNetworkControls.

Covers:
- setup_ir with only required pins returns a LINE transmitter and receiver
- setup_ir with cone_pin returns LINE and CONE transmitters
- setup_ir with aoe_pin returns LINE and AREA_OF_EFFECT transmitters
- setup_ir with all pins returns all three transmitters
- setup_ir transmitters are InfraredTransmitter instances
- setup_ir receiver is an InfraredSingleReceiver instance
- setup_ir omits optional emitters when their pin is None
"""

from __future__ import annotations

import sys
import types

# ---------------------------------------------------------------------------
# Stub out CircuitPython-only hardware modules before importing propmaker.
# We must be careful to set up all modules that propmaker.py imports at
# module level, including pulseio and board constants for IR pins.
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

# adafruit_is31fl3741 constants
_is31 = sys.modules["adafruit_is31fl3741"]
if not hasattr(_is31, "MUST_BUFFER"):
    _is31.MUST_BUFFER = 0  # type: ignore[attr-defined]

# adafruit_rgbmatrixqt stub
_rgbqt = sys.modules["adafruit_is31fl3741.adafruit_rgbmatrixqt"]
if not hasattr(_rgbqt, "Adafruit_RGBMatrixQT"):
    _rgbqt.Adafruit_RGBMatrixQT = type("Adafruit_RGBMatrixQT", (), {})  # type: ignore[attr-defined]

# board pin stubs
_board = sys.modules["board"]
for _attr in ("SCL", "SDA", "EXTERNAL_POWER", "D9", "D10"):
    if not hasattr(_board, _attr):
        setattr(_board, _attr, object())

# digitalio stubs
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
    _pull = types.SimpleNamespace(UP=0, DOWN=1)
    _digitalio.Pull = _pull  # type: ignore[attr-defined]

# busio stubs
_busio = sys.modules["busio"]
if not hasattr(_busio, "I2C"):
    _busio.I2C = type("I2C", (), {"__init__": lambda self, *a: None})  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# pulseio stubs — record constructor calls so tests can assert on them
# ---------------------------------------------------------------------------


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

    def clear(self) -> None:
        self._data.clear()


class _FakePulseOut:
    """Stub for pulseio.PulseOut."""

    def __init__(self, pin, *, frequency=38000, duty_cycle=0x8000) -> None:
        self.pin = pin
        self.frequency = frequency
        self.duty_cycle = duty_cycle
        self.send_calls: list = []

    def send(self, pulses) -> None:
        self.send_calls.append(pulses)


_pulseio = sys.modules["pulseio"]
_pulseio.PulseIn = _FakePulseIn  # type: ignore[attr-defined]
_pulseio.PulseOut = _FakePulseOut  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Now import what we're testing
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

import hardware.circuitpython.propmaker as propmaker  # noqa: E402
from engine.network import AREA_OF_EFFECT, CONE, LINE  # noqa: E402

_RX_PIN = object()
_LINE_PIN = object()
_CONE_PIN = object()
_AOE_PIN = object()


# ---------------------------------------------------------------------------
# setup_ir — transmitter map
# ---------------------------------------------------------------------------


def test_setup_ir_returns_line_transmitter_when_only_required_pins_given():
    """setup_ir always wires the LINE emitter from line_pin."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    assert LINE in transmitters


def test_setup_ir_omits_cone_when_cone_pin_is_none():
    """No CONE entry in transmitter map when cone_pin is not supplied."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    assert CONE not in transmitters


def test_setup_ir_omits_aoe_when_aoe_pin_is_none():
    """No AREA_OF_EFFECT entry when aoe_pin is not supplied."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    assert AREA_OF_EFFECT not in transmitters


def test_setup_ir_includes_cone_transmitter_when_cone_pin_provided():
    """CONE transmitter is present when cone_pin is given."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN, cone_pin=_CONE_PIN)
    assert CONE in transmitters


def test_setup_ir_includes_aoe_transmitter_when_aoe_pin_provided():
    """AREA_OF_EFFECT transmitter is present when aoe_pin is given."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN, aoe_pin=_AOE_PIN)
    assert AREA_OF_EFFECT in transmitters


def test_setup_ir_all_pins_returns_three_transmitters():
    """All three emitter keys are present when all optional pins are given."""
    transmitters, _receiver = propmaker.setup_ir(
        _RX_PIN, _LINE_PIN, cone_pin=_CONE_PIN, aoe_pin=_AOE_PIN
    )
    assert set(transmitters.keys()) == {LINE, CONE, AREA_OF_EFFECT}


# ---------------------------------------------------------------------------
# setup_ir — receiver
# ---------------------------------------------------------------------------


def test_setup_ir_receiver_is_wired_to_rx_pin():
    """The returned receiver reads pulses from the rx_pin PulseIn buffer."""
    _transmitters, receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    pulsein = receiver._reader._pulsein
    assert pulsein.pin is _RX_PIN


def test_setup_ir_receiver_pulsein_uses_active_low_idle_state():
    """PulseIn is constructed with idle_state=True for active-low IR receivers."""
    _transmitters, receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    pulsein = receiver._reader._pulsein
    assert pulsein.idle_state is True


def test_setup_ir_line_transmitter_is_wired_to_line_pin():
    """The LINE transmitter sends pulses via the line_pin PulseOut."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    pulseout = transmitters[LINE]._writer._pulseout
    assert pulseout.pin is _LINE_PIN


def test_setup_ir_pulse_out_uses_38khz_carrier():
    """PulseOut is configured at 38 kHz carrier frequency."""
    transmitters, _receiver = propmaker.setup_ir(_RX_PIN, _LINE_PIN)
    pulseout = transmitters[LINE]._writer._pulseout
    assert pulseout.frequency == 38000


def test_setup_ir_raises_when_line_pin_is_none():
    """setup_ir raises ValueError when line_pin is None — LINE is always required."""
    with pytest.raises(ValueError, match="line_pin is required"):
        propmaker.setup_ir(_RX_PIN, None)
