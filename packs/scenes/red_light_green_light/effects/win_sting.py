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
        clips={EffectVerb.START: AudioPlaybackConfig(name="scene.win_sting_start", loop=False)}
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.TRIPLE_CLICK])}),
)
