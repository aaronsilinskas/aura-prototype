"""Tag scene "reload_complete" effect — audio + vibration sting for a finished reload.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` so it
layers over the restored ``GLOBAL.BUFF`` ammo bar without a pixel conflict.
One-shot with ``stops_effect=True`` so the effect (and its vibration) ends
when the clip finishes.
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

_RELOAD_COMPLETE_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="reload_complete", loop=False, stops_effect=True),
    }
)

_RELOAD_COMPLETE_VIBRATION = EffectVibration(
    patterns={"start": VibrationConfig([VibrationConfig.DOUBLE_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_RELOAD_COMPLETE_AUDIO,
            vibration=_RELOAD_COMPLETE_VIBRATION,
        )


BUILD = _Builder()
