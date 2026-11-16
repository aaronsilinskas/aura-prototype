"""The RLGL warning sting's own look: black to yellow, split 0.3 / 0.4 / 0.3
of its pulse duration, with no off phase."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, EffectVerb, PixelBuffer
from packs.effects.basic.helpers.pulse_effect import PulseEffect
from packs.scenes.red_light_green_light.effects import warning_sting

_YELLOW = 0xFFFF00


_HALF_YELLOW = 0x7F7F00


def _sting(pulse_duration: float, heard: list[EffectVerb] | None = None) -> Effect:
    listeners = [heard.append] if heard is not None else []
    return warning_sting.BUILD(
        "scene.warning_sting",
        EffectConfig(resolution=4, options={"pulse_duration": pulse_duration}, listeners=listeners),
    )


def _color_at(effect: Effect, elapsed: float) -> int:
    assert effect.pixels is not None
    effect.pixels.update(elapsed)
    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    return buf[0]


def test_holds_full_yellow_through_the_middle_four_tenths_of_the_pulse() -> None:
    assert _color_at(_sting(2.0), 0.61) == _YELLOW
    assert _color_at(_sting(2.0), 1.39) == _YELLOW


def test_starts_black() -> None:
    assert _color_at(_sting(2.0), 0.0) == 0x000000


def test_brightens_over_the_first_three_tenths_of_the_pulse() -> None:
    assert _color_at(_sting(2.0), 0.3) == _HALF_YELLOW
    assert _color_at(_sting(2.0), 0.59) != _YELLOW


def test_darkens_over_the_last_three_tenths_of_the_pulse() -> None:
    assert _color_at(_sting(2.0), 1.41) != _YELLOW
    assert _color_at(_sting(2.0), 1.7) == _HALF_YELLOW


def test_the_next_pulse_brightens_straight_after_with_no_off_phase() -> None:
    assert _color_at(_sting(2.0), 2.3) == _HALF_YELLOW


def test_peaks_once_three_tenths_into_the_pulse() -> None:
    heard: list[EffectVerb] = []
    effect = _sting(2.0, heard)
    assert effect.pixels is not None

    effect.pixels.update(0.59)
    assert heard == []
    effect.pixels.update(0.02)
    assert heard == [PulseEffect.PEAK]
