from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from engine.effects.builder import EffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_GOLD_PALETTE: Final = PaletteLUT256(bytes([0, 0x00, 0x00, 0x00, 255, 0xFF, 0xD7, 0x00]))

# Phase durations in seconds
_BRIGHTEN: Final = 0.2
_ON: Final = 0.4
_DARKEN: Final = 0.3
_OFF: Final = 0.1

_LEVEL_UP_AUDIO: Final = EffectAudio(
    clips={EffectVerb.START: AudioPlaybackConfig(name="scene.level_up_start", loop=False)}
)

_LEVEL_UP_HAPTIC: Final = EffectHaptic(
    patterns={EffectVerb.START: HapticPattern([HapticPattern.DOUBLE_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        layer = PulseLayer(_BRIGHTEN, _ON, _DARKEN, _OFF)
        return Effect(
            name=name,
            pixels=PulseEffect(layer, _GOLD_PALETTE, config),
            audio=_LEVEL_UP_AUDIO,
            haptic=_LEVEL_UP_HAPTIC,
        )


BUILD = _Builder()
