"""Tag scene "go" effect — one-shot GO cue fired the instant Playing begins.

No pixel output — issued with ``add_effect`` so it layers over the
freshly-issued HP/ammo bars without a pixel conflict.
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
        clips={EffectVerb.START: AudioPlaybackConfig(name="scene.go_start", loop=False)}
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.STRONG_BUZZ])}),
)
