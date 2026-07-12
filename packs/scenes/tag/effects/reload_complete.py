"""Tag scene "reload_complete" effect — audio + haptic sting for a finished reload.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` so it
layers over the restored ``GLOBAL.BUFF`` ammo bar without a pixel conflict.
One-shot with ``stops_effect=True`` so the effect (and its haptic) ends
when the clip finishes.
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

_RELOAD_COMPLETE_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="reload_complete", loop=False, stops_effect=True),
    }
)

_RELOAD_COMPLETE_HAPTIC = EffectHaptic(
    patterns={"start": HapticPattern([HapticPattern.DOUBLE_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_RELOAD_COMPLETE_AUDIO,
            haptic=_RELOAD_COMPLETE_HAPTIC,
        )


BUILD = _Builder()
