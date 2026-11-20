"""Tag scene "reload_complete" effect — audio + haptic sting for a finished reload.

No pixel output — issued with ``add_effect`` so it
layers over the restored ``GLOBAL.BUFF`` ammo bar without a pixel conflict.
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
            EffectVerb.START: AudioPlaybackConfig(name="scene.reload_complete", loop=False),
        }
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.DOUBLE_CLICK])}),
)
