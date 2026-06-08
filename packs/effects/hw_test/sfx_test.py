from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder

_SFX_TEST_AUDIO = EffectAudio(
    clips={"start": AudioPlaybackConfig(name="sfx_test_start", loop=False)}
)

_SFX_TEST_VIBRATION = EffectVibration(
    patterns={"start": VibrationConfig([VibrationConfig.STRONG_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            pixels=None,
            audio=_SFX_TEST_AUDIO,
            vibration=_SFX_TEST_VIBRATION,
        )


BUILD = _Builder()
