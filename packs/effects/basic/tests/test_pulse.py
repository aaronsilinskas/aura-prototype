"""Unit tests for packs.effects.basic.pulse."""

from __future__ import annotations

import pytest

from effects.render import EffectConfig, PixelBuffer


def _config(level: int = 10, options: dict | None = None) -> EffectConfig:
    return EffectConfig(level=level, resolution=16, options=options or {})


def _build(level: int = 10, options: dict | None = None):
    from packs.effects.basic.pulse import BUILD

    return BUILD("basic.pulse", _config(level, options))


def _render(renderer, pixel_count: int = 4) -> list:
    buf = PixelBuffer(pixel_count)
    renderer.render(buf)
    return list(buf)


# --- Builder ---


def test_pulse_renderer_name_is_basic_pulse() -> None:
    renderer = _build()
    assert renderer.name == "basic.pulse"


# --- Phase: BRIGHTEN at elapsed 0.0 shows start color ---


def test_pulse_at_elapsed_zero_custom_start_color() -> None:
    renderer = _build(options={"start_color": 0xFF0000, "end_color": 0x0000FF})
    renderer.update(0.0)
    pixels = _render(renderer)
    assert all(p == 0xFF0000 for p in pixels)


# --- Phase: end of BRIGHTEN shows end color ---


def test_pulse_at_end_of_brighten_pixels_equal_end_color() -> None:
    # brighten=0.5, on=0.5, darken=0.5, off=0.5 — at elapsed=0.5 we enter ON
    renderer = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    renderer.update(0.5)
    pixels = _render(renderer)
    assert all(p == 0xFFFFFF for p in pixels)


# --- Phase: mid-BRIGHTEN per-channel interpolation ---


def test_pulse_mid_brighten_interpolates_colors_correctly() -> None:
    # brighten=0.5, advance 0.25s → t=0.5
    # start=0x000000, end=0xFFFFFF → each channel: int(0 + 255 * 0.5) = 127 = 0x7F
    renderer = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF})
    renderer.update(0.25)
    pixels = _render(renderer)
    assert all(p == 0x7F7F7F for p in pixels)


# --- Phase: ON holds end color ---


def test_pulse_during_on_phase_pixels_hold_end_color() -> None:
    # brighten=0.5, on=0.5 — at elapsed=0.75 we are mid-ON
    renderer = _build(options={"start_color": 0x000000, "end_color": 0xFF8040})
    renderer.update(0.75)
    pixels = _render(renderer)
    assert all(p == 0xFF8040 for p in pixels)


# --- Phase: after full cycle returns to start color ---


def test_pulse_after_full_cycle_pixels_return_to_start_color() -> None:
    # default cycle_total=2.0, advance exactly 2.0 → wraps to 0.0 → start_color
    renderer = _build(options={"start_color": 0x112233, "end_color": 0xFFFFFF})
    renderer.update(2.0)
    pixels = _render(renderer)
    assert all(p == 0x112233 for p in pixels)


# --- Level scaling ---


def test_pulse_level_scaling_applied_to_start_color() -> None:
    # start=0xFFFFFF, level=1: int(255 * 0.1) = 25 = 0x19
    renderer = _build(
        level=1,
        options={
            "start_color": 0xFFFFFF,
            "end_color": 0x000000,
            "brighten_duration": 0.0,
            "on_duration": 0.0,
            "darken_duration": 0.0,
            "off_duration": 1.0,
        },
    )
    renderer.update(0.5)  # mid-OFF phase
    pixels = _render(renderer)
    assert all(p == 0x191919 for p in pixels)


def test_pulse_level_scaling_applied_to_end_color() -> None:
    # end=0xFFFFFF, level=1: int(255 * 0.1) = 25 = 0x19
    renderer = _build(
        level=1,
        options={
            "start_color": 0x000000,
            "end_color": 0xFFFFFF,
            "brighten_duration": 0.0,
            "on_duration": 1.0,
        },
    )
    renderer.update(0.5)  # mid-ON phase
    pixels = _render(renderer)
    assert all(p == 0x191919 for p in pixels)


# --- Default options ---


def test_pulse_default_end_color_appears_at_on_phase() -> None:
    from packs.effects.basic.pulse import BUILD

    renderer = BUILD("basic.pulse", EffectConfig(level=10, resolution=16))
    renderer.update(0.75)  # past brighten(0.5) + into on(0.5)
    pixels = _render(renderer)
    assert all(p == 0xFFFFFF for p in pixels)


# --- off_duration=0.0 ---


def test_pulse_darken_phase_fades_correctly_when_off_duration_is_zero() -> None:
    # cycle=brighten(0.5)+on(0.5)+darken(0.5)+off(0.0)=1.5
    renderer = _build(options={"start_color": 0x000000, "end_color": 0xFFFFFF, "off_duration": 0.0})
    # At elapsed=1.4 (in DARKEN, near end): t=(1.4-1.0)/0.5=0.8
    # r=int(255+(0-255)*0.8)=int(51.0)=51=0x33
    renderer.update(1.4)
    pixels = _render(renderer)
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
