from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_WARNING_STING_VIBRATION = EffectVibration(
    patterns={"peak": VibrationConfig([VibrationConfig.STRONG_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _pulse(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=EffectAudio(clips={"peak": AudioPlaybackConfig(name=name + "_peak", loop=False)}),
            vibration=_WARNING_STING_VIBRATION,
        )


BUILD = _Builder()
