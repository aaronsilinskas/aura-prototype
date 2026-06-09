try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectPixels,
    EffectVibration,
    PixelBuffer,
    VibrationConfig,
)
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

# Gold: bright gold flash from black to #FFD700
_BLACK: Final = 0x000000
_GOLD: Final = 0xFFD700

_GOLD_PALETTE: Final = PaletteLUT256(
    bytes(
        [
            0,
            (_BLACK >> 16) & 0xFF,
            (_BLACK >> 8) & 0xFF,
            _BLACK & 0xFF,
            255,
            (_GOLD >> 16) & 0xFF,
            (_GOLD >> 8) & 0xFF,
            _GOLD & 0xFF,
        ]
    )
)

# Timing: fast flash — brighten 0.2s, hold 0.4s, fade 0.3s, off 0.1s = 1.0s total
_BRIGHTEN: Final = 0.2
_ON: Final = 0.4
_DARKEN: Final = 0.3
_OFF: Final = 0.1
_CYCLE_TOTAL: Final = _BRIGHTEN + _ON + _DARKEN + _OFF

# Pre-computed phase thresholds used in the update hot path
_T_ON: Final = _BRIGHTEN
_T_DARKEN: Final = _BRIGHTEN + _ON
_T_OFF: Final = _BRIGHTEN + _ON + _DARKEN

# Pre-computed inverse denominators for the transition phases
_INV_BRIGHTEN: Final = 1.0 / _BRIGHTEN
_INV_DARKEN: Final = 1.0 / _DARKEN

_LEVEL_UP_AUDIO: Final = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="level_up_start", loop=False)}
)

_LEVEL_UP_VIBRATION: Final = EffectVibration(
    patterns={"start": VibrationConfig([VibrationConfig.DOUBLE_CLICK])}
)


class _LevelUpPixels(EffectPixels):
    """Gold flash that brightens, holds, then fades over ~1 second."""

    __slots__ = ("_color", "_elapsed")

    def __init__(self) -> None:
        self._elapsed: float = 0.0
        self._color: int = 0

    def update(self, elapsed: float) -> None:
        self._elapsed += elapsed
        t = self._elapsed % _CYCLE_TOTAL
        if t < _T_ON:
            frac = t * _INV_BRIGHTEN
        elif t < _T_DARKEN:
            frac = 1.0
        elif t < _T_OFF:
            frac = 1.0 - (t - _T_DARKEN) * _INV_DARKEN
        else:
            frac = 0.0
        self._color = _GOLD_PALETTE.lookup(frac)

    def render(self, output: PixelBuffer) -> None:
        color = self._color
        for i in range(len(output)):
            output[i] = color


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=_LevelUpPixels(),
            audio=_LEVEL_UP_AUDIO,
            vibration=_LEVEL_UP_VIBRATION,
        )


BUILD = _Builder()
