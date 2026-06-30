"""Tag scene "dry_fire" effect — audio + vibration sting for an empty-magazine trigger pull.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` on
``Scope.DIRECTIONAL`` so it layers alongside the ``Global.BUFF`` reload it
accompanies without a pixel conflict. One-shot with ``stops_effect=True`` so
the effect (and its vibration) ends when the clip finishes. Deliberately
lighter than ``scene.fire_shot`` — a soft bump rather than a double click —
since no shot was actually fired.
"""

from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder

_DRY_FIRE_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="dry_fire_start", loop=False, stops_effect=True),
    }
)

_DRY_FIRE_VIBRATION = EffectVibration(
    patterns={"start": VibrationConfig([VibrationConfig.SOFT_BUMP])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_DRY_FIRE_AUDIO,
            vibration=_DRY_FIRE_VIBRATION,
        )


BUILD = _Builder()
