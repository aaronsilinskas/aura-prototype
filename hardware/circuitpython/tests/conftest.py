"""Stub out CircuitPython-only hardware modules so CPython can import audio_output."""

import sys
import types

for _name in ("audiobusio", "audiocore", "audiomixer", "board", "busio"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

# board constants needed by AudioEffectOutput.__init__
_board = sys.modules["board"]
for _attr in ("I2S_BIT_CLOCK", "I2S_WORD_SELECT", "I2S_DATA"):
    if not hasattr(_board, _attr):
        setattr(_board, _attr, object())


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
