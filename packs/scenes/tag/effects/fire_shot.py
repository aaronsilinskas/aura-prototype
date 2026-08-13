"""Tag scene "fire_shot" effect — one-shot felt feedback for a Button-A shot.

Built on ``basic.solid``: a bright flash of color, layered with a one-shot
``scene.fire_shot_start`` audio clip (``stops_effect=True`` so the whole effect —
pixels and haptic included — ends when the clip finishes, returning
``Scope.DIRECTIONAL`` to dark) and a strong haptic pulse.
"""

from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder
from packs.effects.basic.solid import SolidBuilder

_solid = SolidBuilder()

_FIRE_SHOT_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="scene.fire_shot_start", loop=False, stops_effect=True)
    }
)

_FIRE_SHOT_HAPTIC = EffectHaptic(patterns={"start": HapticPattern([HapticPattern.STRONG_CLICK])})

_FLASH_COLOR = 0xFFFFFF


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base_config = EffectConfig(resolution=config.resolution, options={"color": _FLASH_COLOR})
        base = _solid(name, base_config)
        return Effect(
            name=name,
            pixels=base.pixels,
            audio=_FIRE_SHOT_AUDIO,
            haptic=_FIRE_SHOT_HAPTIC,
        )


BUILD = _Builder()
