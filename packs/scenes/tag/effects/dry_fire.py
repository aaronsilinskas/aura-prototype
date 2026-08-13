"""Tag scene "dry_fire" effect — audio + haptic sting for an empty-magazine trigger pull.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` on
``Scope.DIRECTIONAL`` so it layers alongside the ``Global.BUFF`` reload it
accompanies without a pixel conflict. One-shot with ``stops_effect=True`` so
the effect (and its haptic) ends when the clip finishes. Deliberately
lighter than ``scene.fire_shot`` — a soft bump rather than a double click —
since no shot was actually fired.
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

_DRY_FIRE_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="scene.dry_fire_start", loop=False, stops_effect=True),
    }
)

_DRY_FIRE_HAPTIC = EffectHaptic(patterns={"start": HapticPattern([HapticPattern.SOFT_BUMP])})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_DRY_FIRE_AUDIO,
            haptic=_DRY_FIRE_HAPTIC,
        )


BUILD = _Builder()
