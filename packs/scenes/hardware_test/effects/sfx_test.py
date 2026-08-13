from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder

_SFX_TEST_AUDIO = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="scene.sfx_test_start", loop=False)}
)

_SFX_TEST_HAPTIC = EffectHaptic(patterns={"start": HapticPattern([HapticPattern.STRONG_CLICK])})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_SFX_TEST_AUDIO,
            haptic=_SFX_TEST_HAPTIC,
        )


BUILD = _Builder()
