from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import EffectBuilder

_WIN_STING_HAPTIC = EffectHaptic(
    patterns={
        EffectVerb.START: HapticPattern(
            [
                HapticPattern.TRIPLE_CLICK,
            ]
        )
    }
)

_WIN_STING_AUDIO = EffectAudio(
    clips={
        EffectVerb.START: AudioPlaybackConfig(
            name="scene.win_sting_start", loop=False, stops_effect=True
        )
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
