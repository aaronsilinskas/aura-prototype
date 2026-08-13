try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect

# Gold flash: black → #FFD700
_GOLD_PALETTE: Final = PaletteLUT256(bytes([0, 0x00, 0x00, 0x00, 255, 0xFF, 0xD7, 0x00]))

# Phase thresholds (cumulative seconds): brighten 0.2s, hold 0.4s, fade 0.3s, off 0.1s
_T_ON: Final = 0.2
_T_DARKEN: Final = 0.6
_T_OFF: Final = 0.9
_CYCLE_TOTAL: Final = 1.0

_LEVEL_UP_AUDIO: Final = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="scene.level_up_start", loop=False)}
)

_LEVEL_UP_HAPTIC: Final = EffectHaptic(
    patterns={"start": HapticPattern([HapticPattern.DOUBLE_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        layer = PulseLayer(_T_ON, _T_DARKEN, _T_OFF, _CYCLE_TOTAL)
        return Effect(
            name=name,
            pixels=PulseEffect(layer, _GOLD_PALETTE, config),
            audio=_LEVEL_UP_AUDIO,
            haptic=_LEVEL_UP_HAPTIC,
        )


BUILD = _Builder()
