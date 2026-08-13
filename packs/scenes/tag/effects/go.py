"""Tag scene "go" effect — one-shot GO cue fired the instant Playing begins.

No pixel output (``Effect.pixels = None``) — issued with ``add_effect`` so it
layers over the freshly-issued HP/ammo bars without a pixel conflict.
One-shot with ``stops_effect=True`` so the effect (and its haptic) ends
when the clip finishes — a haptic-only one-shot has nothing of its own to
terminate it, so the audio clip's natural end is what tears it down.
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

_GO_AUDIO = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="scene.go_start", loop=False, stops_effect=True)}
)

_GO_HAPTIC = EffectHaptic(patterns={"start": HapticPattern([HapticPattern.STRONG_BUZZ])})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_GO_AUDIO,
            haptic=_GO_HAPTIC,
        )


BUILD = _Builder()
