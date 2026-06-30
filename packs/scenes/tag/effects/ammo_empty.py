"""Tag scene "ammo_empty" effect — looping red pulse shown while ammo is empty.

Built on ``basic.pulse``: a smooth black->red brighten/darken fade, not a hard
blink. Pulse phase durations are baked in as this effect's own defaults
(callers issue ``scene.ammo_empty`` with no options) rather than being read
from caller-supplied options, so the look is consistent wherever the ammo bar
goes empty. Self-looping via ``PulseLayer``, with no ``stops_effect`` audio —
the effect runs until ``Global.BUFF`` is replaced (by ``scene.reload`` or a
fresh ammo bar) or torn down.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from effects.effect import Effect, EffectConfig
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_DEFAULT_START_COLOR: Final = 0x000000
_DEFAULT_END_COLOR: Final = 0xFF0000
_DEFAULT_BRIGHTEN_DURATION: Final = 0.6
_DEFAULT_ON_DURATION: Final = 0.0
_DEFAULT_DARKEN_DURATION: Final = 0.6
_DEFAULT_OFF_DURATION: Final = 0.0


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pulse_options = {
            "start_color": _DEFAULT_START_COLOR,
            "end_color": _DEFAULT_END_COLOR,
            "brighten_duration": _DEFAULT_BRIGHTEN_DURATION,
            "on_duration": _DEFAULT_ON_DURATION,
            "darken_duration": _DEFAULT_DARKEN_DURATION,
            "off_duration": _DEFAULT_OFF_DURATION,
        }
        pulse_config = EffectConfig(resolution=config.resolution, options=pulse_options)
        base = _pulse(name, pulse_config)
        return Effect(name=base.name, pixels=base.pixels)


BUILD = _Builder()
