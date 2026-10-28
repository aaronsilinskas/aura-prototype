"""Tests for _setup_ir in device_builder — the CircuitPython half of the IR wiring.

_setup_ir builds one PulseIn-backed reader per rx pin and hands the rest to
the shared wiring, whose gate, receiver, transmitter and codec behaviour is
covered in ``hardware/shared/tests/test_ir_wiring.py``. Writer *selection*
(the ``rp2pio`` import-probe inside ``_make_writer``) is exercised separately
in ``test_setup_ir_pio.py``; these tests wire no emitter, so they never reach
the writer path. build_hardware-level radio and IR integration/narration coverage (config
gating, hard-error and disabled/absent-section narration, and the ir/radio
narration lines) lives in test_device_builder_radio_ir.py (#779) instead.
"""

from __future__ import annotations

import sys
import types
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub out CircuitPython-only hardware modules before importing device_builder.
# We must be careful to set up all modules that device_builder.py imports at
# module level, including a minimal pulseio (only PulseIn is touched, since
# these tests wire no emitter and so never build a PulseOut-backed writer).
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
for _attr in ("SCL", "SDA", "D9", "D10"):
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
# pulseio.PulseIn stub — the receiver's rx-side wiring. No PulseOut stub is
# needed: no test here wires an emitter, so pulseio.PulseOut is never built.
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


_pulseio = sys.modules["pulseio"]
_pulseio.PulseIn = _FakePulseIn  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Now import what we're testing
# ---------------------------------------------------------------------------


from hardware.circuitpython.device_builder import _setup_ir  # noqa: E402
from hardware.circuitpython.infrared_io import PulseInReader  # noqa: E402

_RX_PIN = object()


def _wired_readers(transceiver: object) -> list:
    """Return the private ``_readers`` list wired onto the transceiver's receiver.

    InfraredTransceiver exposes no public getter for a receiver's readers, so
    these tests reach into that private field, only through this helper, to
    pin which PulseIn each reader wraps.
    """
    return transceiver._receiver._readers


def test_setup_ir_receiver_is_wired_to_rx_pin():
    """The returned receiver reads pulses from the rx_pin PulseIn buffer."""
    transceiver, _writer_kind = _setup_ir([_RX_PIN], {})
    pulsein = _wired_readers(transceiver)[0]._pulsein
    assert pulsein.pin is _RX_PIN


def test_setup_ir_receiver_pulsein_uses_active_low_idle_state():
    """PulseIn is constructed with idle_state=True for active-low IR receivers."""
    transceiver, _writer_kind = _setup_ir([_RX_PIN], {})
    pulsein = _wired_readers(transceiver)[0]._pulsein
    assert pulsein.idle_state is True


def test_setup_ir_builds_one_pulsein_reader_per_rx_pin() -> None:
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        transceiver, _writer_kind = _setup_ir(
            rx_pins=[MagicMock(), MagicMock(), MagicMock()], emitter_pins={}
        )

    readers = _wired_readers(transceiver)
    assert len(readers) == 3
    assert all(isinstance(reader, PulseInReader) for reader in readers)
