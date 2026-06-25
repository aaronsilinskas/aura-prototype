"""Stub out CircuitPython-only hardware modules so CPython can import audio_output."""

import sys
import types

for _name in (
    "audiobusio",
    "audiocore",
    "audiomixer",
    "board",
    "busio",
    "digitalio",
    "neopixel",
    "pulseio",
):
    sys.modules.setdefault(_name, types.ModuleType(_name))

_board = sys.modules["board"]

# ---------------------------------------------------------------------------
# adafruit_is31fl3741 stub — minimal for device_builder imports
# ---------------------------------------------------------------------------

_is31_mod = types.ModuleType("adafruit_is31fl3741")
_is31_mod.MUST_BUFFER = 1  # type: ignore[attr-defined]
sys.modules.setdefault("adafruit_is31fl3741", _is31_mod)

_rgbmatrix_mod = types.ModuleType("adafruit_is31fl3741.adafruit_rgbmatrixqt")
_rgbmatrix_mod.Adafruit_RGBMatrixQT = type(  # type: ignore[attr-defined]
    "Adafruit_RGBMatrixQT", (), {}
)
sys.modules.setdefault("adafruit_is31fl3741.adafruit_rgbmatrixqt", _rgbmatrix_mod)


# ---------------------------------------------------------------------------
# adafruit_drv2605 stub — minimal Effect and Pause for Drv2605EffectOutput tests
# ---------------------------------------------------------------------------


class _Effect:
    """Minimal stub for adafruit_drv2605.Effect with equality comparison."""

    __slots__ = ("id",)

    def __init__(self, id: int) -> None:
        self.id = id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Effect):
            return self.id == other.id
        return NotImplemented

    def __repr__(self) -> str:
        return f"Effect({self.id})"


class _Pause:
    """Minimal stub for adafruit_drv2605.Pause with equality comparison."""

    __slots__ = ("duration",)

    def __init__(self, duration: int) -> None:
        self.duration = duration

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Pause):
            return self.duration == other.duration
        return NotImplemented

    def __repr__(self) -> str:
        return f"Pause({self.duration})"


_drv2605_mod = types.ModuleType("adafruit_drv2605")
_drv2605_mod.Effect = _Effect  # type: ignore[attr-defined]
_drv2605_mod.Pause = _Pause  # type: ignore[attr-defined]
sys.modules["adafruit_drv2605"] = _drv2605_mod
