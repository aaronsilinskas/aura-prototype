from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder

BUILD = ComposedEffectBuilder(
    # Shared with every scene's game-over moment -- see basic/sounds/game_over_sting_start.wav.
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
