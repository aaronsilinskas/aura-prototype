"""Unit tests for packs.effects.basic.pulse."""

from __future__ import annotations

import pytest

from effects.effect import EffectConfig, PixelBuffer


def _config(options: dict | None = None) -> EffectConfig:
    opts = dict(options) if options else {}
    return EffectConfig(resolution=16, options=opts)


def _build(options: dict | None = None):
    from packs.effects.basic.pulse import BUILD

    return BUILD("basic.pulse", _config(options))


def _render(effect, pixel_count: int = 4) -> list:
    buf = PixelBuffer(pixel_count)
    effect.pixels.render(buf)
    return list(buf)


# --- Builder ---


def test_pulse_effect_name_is_basic_pulse() -> None:
    effect = _build()
    assert effect.name == "basic.pulse"


# --- Phase: BRIGHTEN at elapsed 0.0 shows start color ---


def test_pulse_at_elapsed_zero_custom_start_color() -> None:
    effect = _build(options={"start_color": 0xFF0000, "end_color": 0x0000FF})
    effect.pixels.update(0.0)
    pixels = _render(effect)
    assert all(p == 0xFF0000 for p in pixels)


# --- Phase: end of BRIGHTEN shows end color ---


def test_pulse_at_end_of_brighten_pixels_equal_end_color() -> None:
    # brighten=0.5, on=0.5, darken=0.5, off=0.5 — at elapsed=0.5 we enter ON
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    effect.pixels.update(0.5)
    pixels = _render(effect)
    assert all(p == 0xFFFFFF for p in pixels)


# --- Phase: mid-BRIGHTEN per-channel interpolation ---


def test_pulse_mid_brighten_interpolates_colors_correctly() -> None:
    # brighten=0.5, advance 0.25s → t=0.5
    # start=0x000000, end=0xFFFFFF → each channel: int(0 + 255 * 0.5) = 127 = 0x7F
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    effect.pixels.update(0.25)
    pixels = _render(effect)
    assert all(p == 0x7F7F7F for p in pixels)


# --- Phase: ON holds end color ---


def test_pulse_during_on_phase_pixels_hold_end_color() -> None:
    # brighten=0.5, on=0.5 — at elapsed=0.75 we are mid-ON
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFF8040})
    effect.pixels.update(0.75)
    pixels = _render(effect)
    assert all(p == 0xFF8040 for p in pixels)


# --- Phase: after full cycle returns to start color ---


def test_pulse_after_full_cycle_pixels_return_to_start_color() -> None:
    # default cycle_total=2.0, advance exactly 2.0 → wraps to 0.0 → start_color
    effect = _build(options={"start_color": 0x112233, "end_color": 0xFFFFFF})
    effect.pixels.update(2.0)
    pixels = _render(effect)
    assert all(p == 0x112233 for p in pixels)


# --- Raw color pass-through ---


def test_pulse_stores_start_color_unscaled() -> None:
    # start=0x7F3F1F stored raw (not brightness-scaled)
    effect = _build(
        options={
            "start_color": 0x7F3F1F,
            "end_color": 0x000000,
            "brighten_duration": 0.0,
            "on_duration": 0.0,
            "darken_duration": 0.0,
            "off_duration": 1.0,
        }
    )
    effect.pixels.update(0.5)  # mid-OFF phase → start_color
    pixels = _render(effect)
    assert all(p == 0x7F3F1F for p in pixels)


def test_pulse_stores_end_color_unscaled() -> None:
    # end=0x7F3F1F stored raw (not brightness-scaled)
    effect = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0x7F3F1F,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
        }
    )
    effect.pixels.update(0.5)  # mid-ON phase → end_color
    pixels = _render(effect)
    assert all(p == 0x7F3F1F for p in pixels)


def test_pulse_ignores_brightness_option() -> None:
    # brightness option is silently ignored; raw end_color is stored as-is
    effect_with_brightness = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
            "brightness": 0.5,
        }
    )
    effect_without_brightness = _build(
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
        }
    )
    effect_with_brightness.pixels.update(0.5)
    effect_without_brightness.pixels.update(0.5)
    # both should produce full white since brightness is ignored
    assert _render(effect_with_brightness) == _render(effect_without_brightness)
    assert all(p == 0xFFFFFF for p in _render(effect_without_brightness))


# --- Default options ---


def test_pulse_default_end_color_appears_at_on_phase() -> None:
    from packs.effects.basic.pulse import BUILD

    effect = BUILD("basic.pulse", EffectConfig(resolution=16))
    effect.pixels.update(0.75)  # past brighten(0.5) + into on(0.5)
    pixels = _render(effect)
    assert all(p == 0xFFFFFF for p in pixels)


# --- off_duration=0.0 ---


def test_pulse_darken_phase_fades_correctly_when_off_duration_is_zero() -> None:
    # cycle=brighten(0.5)+on(0.5)+darken(0.5)+off(0.0)=1.5
    effect = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF, "off_duration": 0.0})
    # At elapsed=1.4 (in DARKEN, near end): t=(1.4-1.0)/0.5=0.8
    # r=int(255+(0-255)*0.8)=int(51.0)=51=0x33
    effect.pixels.update(1.4)
    pixels = _render(effect)
    assert all(p == 0x333333 for p in pixels)


# --- ValueError at build time ---


def test_pulse_negative_brighten_duration_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _build(options={"brighten_duration": -0.1})


def test_pulse_negative_on_duration_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _build(options={"on_duration": -1.0})


def test_pulse_negative_darken_duration_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _build(options={"darken_duration": -0.5})


def test_pulse_negative_off_duration_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _build(options={"off_duration": -0.01})


def test_pulse_all_zero_durations_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _build(
            options={
                "brighten_duration": 0.0,
                "on_duration": 0.0,
                "darken_duration": 0.0,
                "off_duration": 0.0,
            }
        )
