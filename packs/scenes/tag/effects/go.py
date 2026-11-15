"""Tag scene "go" effect — one-shot GO cue fired the instant Playing begins.

No pixel output — issued with ``add_effect`` so it layers over the
freshly-issued HP/ammo bars without a pixel conflict. One-shot with
``stops_effect=True`` so the effect (and its haptic) ends when the clip
finishes — a haptic-only one-shot has nothing of its own to terminate it, so
the audio clip's natural end is what tears it down.
"""

from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder

BUILD = ComposedEffectBuilder(
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(
                name="scene.go_start", loop=False, stops_effect=True
            )
        }
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.STRONG_BUZZ])}),
)
