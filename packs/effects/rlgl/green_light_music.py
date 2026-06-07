from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder

_GREEN_LIGHT_VIBRATION = EffectVibration(
    patterns={
        "start": VibrationConfig(
            [VibrationConfig.DOUBLE_CLICK, VibrationConfig.PAUSE_250, VibrationConfig.SOFT_BUMP]
        )
    }
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=EffectAudio(
                clips={"start": AudioPlaybackConfig(name=name + "_start", loop=True)}
            ),
            vibration=_GREEN_LIGHT_VIBRATION,
        )


BUILD = _Builder()
