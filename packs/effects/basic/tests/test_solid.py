"""Unit tests for packs.effects.basic.solid."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config(color: int | None = None, brightness: float | None = None) -> EffectConfig:
    options: dict = {}
    if color is not None:
        options["color"] = color
    if brightness is not None:
        options["brightness"] = brightness
    return EffectConfig(resolution=16, options=options)


def _render(pixel_count: int = 4, color: int | None = None, brightness: float | None = None):
    from packs.effects.basic.solid import BUILD

    config = _config(color, brightness)
    effect = BUILD("basic.solid", config)
    buf = PixelBuffer(pixel_count)
    effect.render(buf)
    return list(buf)


# --- SolidBuilder ---


def test_solid_build_returns_effect_builder_instance() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.effects.basic.solid import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_solid_effect_name_is_basic_solid() -> None:
    from packs.effects.basic.solid import BUILD

    effect = BUILD("basic.solid", _config())
    assert effect.name == "basic.solid"


# --- Brightness scaling ---


def test_solid_brightness_default_is_full() -> None:
    pixels = _render(color=0xFFFFFF)
    assert all(p == 0xFFFFFF for p in pixels)


def test_solid_brightness_0_5_halves_each_channel() -> None:
    # int(255 * 0.5) = 127 = 0x7F
    pixels = _render(color=0xFFFFFF, brightness=0.5)
    assert all(p == 0x7F7F7F for p in pixels)


def test_solid_brightness_0_0_produces_black() -> None:
    pixels = _render(color=0xFFFFFF, brightness=0.0)
    assert all(p == 0x000000 for p in pixels)


def test_solid_brightness_1_5_clamps_to_full() -> None:
    # out-of-range clamp: 1.5 → 1.0, same as brightness=1.0
    pixels_clamped = _render(color=0xFFFFFF, brightness=1.5)
    pixels_full = _render(color=0xFFFFFF, brightness=1.0)
    assert pixels_clamped == pixels_full


def test_solid_brightness_negative_0_2_clamps_to_black() -> None:
    # out-of-range clamp: -0.2 → 0.0, same as brightness=0.0
    pixels_clamped = _render(color=0xFFFFFF, brightness=-0.2)
    pixels_zero = _render(color=0xFFFFFF, brightness=0.0)
    assert pixels_clamped == pixels_zero


# --- Defaults ---


def test_solid_no_color_option_defaults_to_white() -> None:
    from packs.effects.basic.solid import BUILD

    config = EffectConfig(resolution=16)
    effect = BUILD("basic.solid", config)
    buf = PixelBuffer(4)
    effect.render(buf)
    assert all(p == 0xFFFFFF for p in buf)


# --- Determinism ---


def test_solid_render_is_deterministic() -> None:
    first = _render(color=0x00FF88, brightness=0.7)
    second = _render(color=0x00FF88, brightness=0.7)
    assert first == second
