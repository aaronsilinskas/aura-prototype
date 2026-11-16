"""RLGL scene "warning_sting" effect — looping warning pulse with a sting + click on each peak.

Built on ``basic.pulse``. Takes one option, ``pulse_duration``: seconds per
pulse. The rule behind Red Warning and Green Warning always passes the Game
Level's duration, scaled between the ``warning_pulse_max`` and
``warning_pulse_min`` Settings; the 1-second default is only a fallback and
does not track those Settings.

The effect owns its look: a black->yellow pulse that brightens, holds and
darkens over 0.3 / 0.4 / 0.3 of its duration, with no off phase, so one pulse
runs straight into the next. Any color or phase option a caller passes is
overridden. Each ``PulseEffect.PEAK`` (one per pulse) plays a one-shot
``scene.warning_sting_peak`` clip and a single ``STRONG_CLICK`` buzz.
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

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_pulse = PulseBuilder()

_DEFAULT_PULSE_DURATION: Final = 1.0

# Shares of each pulse spent brightening, holding and darkening.
_BRIGHTEN_SHARE: Final = 0.3
_ON_SHARE: Final = 0.4
_DARKEN_SHARE: Final = 0.3

_WARNING_STING_AUDIO: Final = EffectAudio(
    clips={PulseEffect.PEAK: AudioPlaybackConfig(name="scene.warning_sting_peak", loop=False)}
)

_WARNING_STING_HAPTIC: Final = EffectHaptic(
    patterns={PulseEffect.PEAK: HapticPattern([HapticPattern.STRONG_CLICK])}
)


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pulse = config.get_option("pulse_duration", _DEFAULT_PULSE_DURATION)
        look: dict[str, object] = {
            "start_color": 0x000000,
            "end_color": 0xFFFF00,
            "brighten_duration": pulse * _BRIGHTEN_SHARE,
            "on_duration": pulse * _ON_SHARE,
            "darken_duration": pulse * _DARKEN_SHARE,
            "off_duration": 0.0,
        }
        base = _pulse(name, config.with_options(look))
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=_WARNING_STING_AUDIO,
            haptic=_WARNING_STING_HAPTIC,
        )


BUILD = _Builder()
