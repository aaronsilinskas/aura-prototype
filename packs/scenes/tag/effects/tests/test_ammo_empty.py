"""Unit tests for packs.scenes.tag.effects.ammo_empty."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer
from packs.scenes.tag.effects.ammo_empty import (
    _DEFAULT_BRIGHTEN_DURATION,
    _DEFAULT_DARKEN_DURATION,
    BUILD,
)


def _config(**options) -> EffectConfig:
    return EffectConfig(resolution=16, options=options)


def _build(**options):
    return BUILD("scene.ammo_empty", _config(**options))


def test_ammo_empty_has_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is not None


def test_ammo_empty_starts_at_black_before_any_update() -> None:
    effect = _build()

    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0x000000 for p in buf)


def test_ammo_empty_reaches_full_red_at_the_brighten_duration_boundary() -> None:
    effect = _build()

    effect.pixels.update(_DEFAULT_BRIGHTEN_DURATION)

    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0xFF0000 for p in buf)


def test_ammo_empty_fades_smoothly_rather_than_hard_blinking() -> None:
    effect = _build()
    halfway_through_brighten = _DEFAULT_BRIGHTEN_DURATION / 2

    effect.pixels.update(halfway_through_brighten)

    buf = PixelBuffer(8)
    effect.pixels.render(buf)
    # A hard blink would already be fully red or fully black; a smooth fade sits
    # strictly between the two end colors.
    assert all(0x000000 < p < 0xFF0000 for p in buf)


def test_ammo_empty_pulse_repeats_identically_every_cycle_with_no_caller_options() -> None:
    effect = _build()
    one_cycle = _DEFAULT_BRIGHTEN_DURATION + _DEFAULT_DARKEN_DURATION

    effect.pixels.update(one_cycle)
    buf_after_one_cycle = PixelBuffer(8)
    effect.pixels.render(buf_after_one_cycle)

    effect.pixels.update(one_cycle)
    buf_after_two_cycles = PixelBuffer(8)
    effect.pixels.render(buf_after_two_cycles)

    assert list(buf_after_one_cycle) == list(buf_after_two_cycles)


def test_ammo_empty_carries_no_audio_so_it_cannot_carry_stops_effect() -> None:
    effect = _build()

    assert effect.audio is None
