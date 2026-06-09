from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder

_WIN_STING_VIBRATION = EffectVibration(
    patterns={
        "start": VibrationConfig(
            [
                VibrationConfig.TRIPLE_CLICK,
            ]
        )
    }
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(
            name=name,
            audio=EffectAudio(
                clips={"start": AudioPlaybackConfig(name="win_sting_start", loop=False)}
            ),
            vibration=_WIN_STING_VIBRATION,
        )


BUILD = _Builder()
