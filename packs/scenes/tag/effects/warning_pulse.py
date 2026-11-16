"""Tag scene "warning_pulse" effect — looping countdown pulse with a blip + buzz on each peak.

Built on ``basic.pulse``. Takes one option, ``pulse_duration`` (seconds per
pulse, default ``0.6``), and owns the look: a black->white fade spending half
the pulse brightening and half darkening, with no on or off phase. Any color
or phase option a caller passes is overridden. It then layers on a one-shot
``scene.warning_pulse_peak`` audio clip and a single ``SHARP_CLICK`` buzz
fired on each ``PulseEffect.PEAK`` (one per pulse cycle), so every pulse
buzzes uniformly.
"""

from __future__ import annotations

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

_DEFAULT_PULSE_DURATION = 0.6

_WARNING_PULSE_AUDIO = EffectAudio(
    clips={PulseEffect.PEAK: AudioPlaybackConfig(name="scene.warning_pulse_peak", loop=False)}
)

_WARNING_PULSE_HAPTIC = EffectHaptic(
    patterns={PulseEffect.PEAK: HapticPattern([HapticPattern.SHARP_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        half = config.get_option("pulse_duration", _DEFAULT_PULSE_DURATION) / 2
        look: dict[str, object] = {
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": half,
            "on_duration": 0.0,
            "darken_duration": half,
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
