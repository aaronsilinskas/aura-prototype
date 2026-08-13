from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder

_WIN_STING_HAPTIC = EffectHaptic(
    patterns={
        "start": HapticPattern(
            [
                HapticPattern.TRIPLE_CLICK,
            ]
        )
    }
)

_WIN_STING_AUDIO = EffectAudio(
    clips={
        "start": AudioPlaybackConfig(name="scene.win_sting_start", loop=False, stops_effect=True)
    }
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=_WIN_STING_AUDIO,
            haptic=_WIN_STING_HAPTIC,
        )


BUILD = _Builder()
