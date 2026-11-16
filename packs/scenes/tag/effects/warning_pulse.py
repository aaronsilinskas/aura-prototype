"""Tag scene "warning_pulse" effect — looping countdown pulse with a blip + buzz on each peak.

Built on ``basic.pulse``. Takes one option, ``pulse_duration``: seconds per
pulse. The Starting rule always passes the ``warning_pulse_duration`` Setting;
the 1-second default is only a fallback and does not track that Setting.

The effect owns its look: a black->white fade spending half the pulse
brightening and half darkening, with no on or off phase. Any color or phase
option a caller passes is overridden. Each ``PulseEffect.PEAK`` (one per pulse)
plays a one-shot ``scene.warning_pulse_peak`` clip and a single ``SHARP_CLICK``
buzz, so every pulse buzzes uniformly.
"""

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

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

_pulse = PulseBuilder()

_DEFAULT_PULSE_DURATION: Final = 1.0

# Shares of each pulse spent brightening and darkening.
_BRIGHTEN_SHARE: Final = 0.5
_DARKEN_SHARE: Final = 0.5

_WARNING_PULSE_AUDIO: Final = EffectAudio(
    clips={PulseEffect.PEAK: AudioPlaybackConfig(name="scene.warning_pulse_peak", loop=False)}
)

_WARNING_PULSE_HAPTIC: Final = EffectHaptic(
    patterns={PulseEffect.PEAK: HapticPattern([HapticPattern.SHARP_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pulse = config.get_option("pulse_duration", _DEFAULT_PULSE_DURATION)
        look: dict[str, object] = {
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": pulse * _BRIGHTEN_SHARE,
            "on_duration": 0.0,
            "darken_duration": pulse * _DARKEN_SHARE,
            "off_duration": 0.0,
        }
        base = _pulse(name, config.with_options(look))
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_PULSE_AUDIO,
            haptic=_WARNING_PULSE_HAPTIC,
        )


BUILD = _Builder()
