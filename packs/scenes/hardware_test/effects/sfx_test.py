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

_SFX_TEST_AUDIO = EffectAudio(
    clips={EffectVerb.START: AudioPlaybackConfig(name="scene.sfx_test_start", loop=False)}
)

_SFX_TEST_HAPTIC = EffectHaptic(
    patterns={EffectVerb.START: HapticPattern([HapticPattern.STRONG_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_SFX_TEST_AUDIO,
            haptic=_SFX_TEST_HAPTIC,
        )


BUILD = _Builder()
