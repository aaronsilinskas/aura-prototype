"""A game-over sting for a scene to use as its own effect: the sound plus three strong buzzes."""

from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder

GAME_OVER_STING = ComposedEffectBuilder(
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(name="basic.game_over_sting_start", loop=False)
        }
    ),
    haptic=EffectHaptic(
        patterns={
            EffectVerb.START: HapticPattern(
                [
                    HapticPattern.STRONG_BUZZ,
                    HapticPattern.PAUSE_250,
                    HapticPattern.STRONG_BUZZ,
                    HapticPattern.PAUSE_250,
                    HapticPattern.STRONG_BUZZ,
                ]
            )
        }
    ),
)
