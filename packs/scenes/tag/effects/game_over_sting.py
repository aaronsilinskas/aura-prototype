from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder

_GAME_OVER_HAPTIC = EffectHaptic(
    patterns={
        "start": HapticPattern(
            [
                HapticPattern.STRONG_BUZZ,
                HapticPattern.PAUSE_250,
                HapticPattern.STRONG_BUZZ,
                HapticPattern.PAUSE_250,
                HapticPattern.STRONG_BUZZ,
            ]
        )
    }
)


_GAME_OVER_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(
            name="basic.game_over_sting_start", loop=False, stops_effect=True
        )
    }
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=_GAME_OVER_AUDIO,
            haptic=_GAME_OVER_HAPTIC,
        )


BUILD = _Builder()
