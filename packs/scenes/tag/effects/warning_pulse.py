"""Tag scene "warning_pulse" effect — looping countdown pulse with a blip on each peak.

Built on ``basic.pulse``: forwards all pulse options (colors, phase
durations) to :class:`PulseBuilder`, then layers on a one-shot ``blip``
audio clip fired on each ``"peak"`` event (one per pulse cycle, via
``PulseEffect``).
"""

from __future__ import annotations

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_WARNING_PULSE_AUDIO = EffectAudio(
    clips={"peak": AudioPlaybackConfig(name="warning_pulse_peak", loop=False)}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _pulse(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_PULSE_AUDIO,
        )


BUILD = _Builder()
