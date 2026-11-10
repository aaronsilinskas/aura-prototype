"""Tag scene "warning_pulse" effect — looping countdown pulse with a blip + buzz on each peak.

Built on ``basic.pulse``: forwards all pulse options (colors, phase
durations) to :class:`PulseBuilder`, then layers on a one-shot
``scene.warning_pulse_peak`` audio clip and a single ``SHARP_CLICK`` buzz
fired on each ``PulseEffect.PEAK`` (one per pulse cycle).
The looping pixel effect itself is unchanged — every pulse buzzes uniformly.
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

_WARNING_PULSE_AUDIO = EffectAudio(
    clips={PulseEffect.PEAK: AudioPlaybackConfig(name="scene.warning_pulse_peak", loop=False)}
)

_WARNING_PULSE_HAPTIC = EffectHaptic(
    patterns={PulseEffect.PEAK: HapticPattern([HapticPattern.SHARP_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _pulse(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_PULSE_AUDIO,
            haptic=_WARNING_PULSE_HAPTIC,
        )


BUILD = _Builder()
