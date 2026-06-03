"""Unit tests for packs.effects.basic.solid."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config(level: int, color: int | None = None) -> EffectConfig:
    options: dict = {"level": level}
    if color is not None:
        options["color"] = color
    return EffectConfig(resolution=16, options=options)


def _render(level: int, pixel_count: int = 4, color: int | None = None):
    from packs.effects.basic.solid import BUILD

    config = _config(level, color)
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

    effect = BUILD("basic.solid", _config(5))
    assert effect.name == "basic.solid"


# --- Color scaling ---


def test_solid_level_1_white_produces_dim_pixels() -> None:
    # Each channel: int(255 * 0.1) = 25 = 0x19
    pixels = _render(level=1, color=0xFFFFFF)
    assert all(p == 0x191919 for p in pixels)


def test_solid_level_10_white_produces_full_brightness_pixels() -> None:
    pixels = _render(level=10, color=0xFFFFFF)
    assert all(p == 0xFFFFFF for p in pixels)


def test_solid_level_5_red_scales_red_channel_only() -> None:
    # Red channel: int(255 * 0.5) = 127 = 0x7F; green/blue stay 0
    pixels = _render(level=5, color=0xFF0000)
    assert all(p == 0x7F0000 for p in pixels)


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
    first = _render(level=7, color=0x00FF88)
    second = _render(level=7, color=0x00FF88)
    assert first == second
