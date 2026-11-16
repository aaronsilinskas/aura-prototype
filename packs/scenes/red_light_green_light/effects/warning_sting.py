from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.builder import EffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect
from packs.effects.basic.pulse import PulseBuilder

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

_pulse = PulseBuilder()

# Each pulse brightens, holds and darkens over these shares of its duration,
# with no off phase, so one pulse runs straight into the next.
_BRIGHTEN_SHARE: Final = 0.3
_ON_SHARE: Final = 0.4
_DARKEN_SHARE: Final = 0.3

_WARNING_STING_HAPTIC = EffectHaptic(
    patterns={PulseEffect.PEAK: HapticPattern([HapticPattern.STRONG_CLICK])}
)

_WARNING_STING_AUDIO = EffectAudio(
    clips={PulseEffect.PEAK: AudioPlaybackConfig(name="scene.warning_sting_peak", loop=False)}
)


class _Builder(EffectBuilder):
    """Builds the warning sting: black-to-yellow pulses that click and play
    ``scene.warning_sting_peak`` at each peak.

    Reads ``pulse_duration`` (seconds per pulse, default ``1.0``) from options;
    the colors and phase split are the sting's own.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pulse = config.get_option("pulse_duration", 1.0)
        pulse_config = config.with_options(
            {
                "start_color": 0x000000,
                "end_color": 0xFFFF00,
                "brighten_duration": pulse * _BRIGHTEN_SHARE,
                "on_duration": pulse * _ON_SHARE,
                "darken_duration": pulse * _DARKEN_SHARE,
                "off_duration": 0.0,
            }
        )
        base = _pulse(name, pulse_config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_STING_AUDIO,
            haptic=_WARNING_STING_HAPTIC,
        )


BUILD = _Builder()
