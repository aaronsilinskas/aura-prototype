"""Tag scene "ready" effect — a thin, visual-only pulse.

A simple white pulse (0x000000 -> 0xFFFFFF) used to indicate the device is
idle in the Ready phase, waiting for a button press to start the game.
"""

from __future__ import annotations

from effects.effect import Effect, EffectConfig
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_READY_OPTIONS = {
    "start_color": 0x000000,
    "end_color": 0xFFFFFF,
    "brighten_duration": 0.5,
    "on_duration": 0.2,
    "darken_duration": 0.5,
    "off_duration": 0.2,
}


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        ready_config = EffectConfig(
            resolution=config.resolution,
            options=_READY_OPTIONS,
            listeners=config.listeners,
        )
        return _pulse(name, ready_config)


BUILD = _Builder()
