"""The RLGL warning sting's own look: black to yellow, split 0.3 / 0.4 / 0.3
of its pulse duration, with no off phase.
"""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, EffectVerb, PixelBuffer
from packs.effects.basic.helpers.pulse_effect import PulseEffect
from packs.scenes.red_light_green_light.effects import warning_sting

_YELLOW = 0xFFFF00
_HALF_YELLOW = 0x7F7F00
_NEAR_YELLOW = 0xFAFA00  # 59/60 of the way to yellow


def _sting(options: dict[str, object], heard: list[EffectVerb] | None = None) -> Effect:
    listeners = [heard.append] if heard is not None else []
    return warning_sting.BUILD(
        "scene.warning_sting", EffectConfig(resolution=4, options=options, listeners=listeners)
    )


def _two_second_sting(heard: list[EffectVerb] | None = None) -> Effect:
    return _sting({"pulse_duration": 2.0}, heard)


def _color_at(effect: Effect, elapsed: float) -> int:
    assert effect.pixels is not None
    effect.pixels.update(elapsed)
    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    return buf[0]


def test_warning_sting_starts_black() -> None:
    assert _color_at(_two_second_sting(), 0.0) == 0x000000


def test_warning_sting_brightens_over_the_first_three_tenths_of_the_pulse() -> None:
    assert _color_at(_two_second_sting(), 0.3) == _HALF_YELLOW
    assert _color_at(_two_second_sting(), 0.59) == _NEAR_YELLOW


def test_warning_sting_holds_full_yellow_through_the_middle_four_tenths_of_the_pulse() -> None:
    assert _color_at(_two_second_sting(), 0.61) == _YELLOW
    assert _color_at(_two_second_sting(), 1.39) == _YELLOW


def test_warning_sting_darkens_over_the_last_three_tenths_of_the_pulse() -> None:
    assert _color_at(_two_second_sting(), 1.41) == _NEAR_YELLOW
    assert _color_at(_two_second_sting(), 1.7) == _HALF_YELLOW


def test_warning_sting_brightens_the_next_pulse_straight_after_with_no_off_phase() -> None:
    assert _color_at(_two_second_sting(), 2.3) == _HALF_YELLOW


def test_warning_sting_peaks_once_per_pulse_three_tenths_in() -> None:
    heard: list[EffectVerb] = []
    effect = _two_second_sting(heard)
    assert effect.pixels is not None

    effect.pixels.update(0.59)
    assert heard == []
    effect.pixels.update(0.02)
    assert heard == [PulseEffect.PEAK]
    effect.pixels.update(1.98)
    assert heard == [PulseEffect.PEAK]
    effect.pixels.update(0.02)
    assert heard == [PulseEffect.PEAK, PulseEffect.PEAK]


def test_warning_sting_keeps_its_own_colors_and_split_whatever_the_caller_passes() -> None:
    caller_look: dict[str, object] = {
        "pulse_duration": 2.0,
        "start_color": 0x00FF00,
        "end_color": 0x0000FF,
        "brighten_duration": 0.1,
        "on_duration": 0.1,
        "darken_duration": 0.1,
        "off_duration": 5.0,
    }

    assert _color_at(_sting(caller_look), 0.3) == _HALF_YELLOW
    assert _color_at(_sting(caller_look), 1.0) == _YELLOW


def test_warning_sting_pulses_once_a_second_when_no_pulse_duration_is_passed() -> None:
    assert _color_at(_sting({}), 0.15) == _HALF_YELLOW
    assert _color_at(_sting({}), 0.5) == _YELLOW
    assert _color_at(_sting({}), 1.15) == _HALF_YELLOW
