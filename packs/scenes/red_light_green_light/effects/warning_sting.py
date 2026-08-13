from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_WARNING_STING_HAPTIC = EffectHaptic(patterns={"peak": HapticPattern([HapticPattern.STRONG_CLICK])})

_WARNING_STING_AUDIO = EffectAudio(
    clips={"peak": AudioPlaybackConfig(name="scene.warning_sting_peak", loop=False)}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _pulse(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_STING_AUDIO,
            haptic=_WARNING_STING_HAPTIC,
        )


BUILD = _Builder()
