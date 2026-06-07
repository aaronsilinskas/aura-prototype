"""Unit tests for packs.effects.basic.solid."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config(color: int | None = None) -> EffectConfig:
    options: dict = {}
    if color is not None:
        options["color"] = color
    return EffectConfig(resolution=16, options=options)


def _render(pixel_count: int = 4, color: int | None = None):
    from packs.effects.basic.solid import BUILD

    config = _config(color)
    effect = BUILD("basic.solid", config)
    buf = PixelBuffer(pixel_count)
    effect.pixels.render(buf)
    return list(buf)


def test_solid_build_returns_effect_builder_instance() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.effects.basic.solid import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_solid_effect_name_is_basic_solid() -> None:
    from packs.effects.basic.solid import BUILD

    effect = BUILD("basic.solid", _config())
    assert effect.name == "basic.solid"


# --- Raw color pass-through ---


def test_solid_stores_raw_color_unscaled() -> None:
    pixels = _render(color=0xFFFFFF)
    assert all(p == 0xFFFFFF for p in pixels)


def test_solid_stores_partial_color_unscaled() -> None:
    pixels = _render(color=0x7F7F7F)
    assert all(p == 0x7F7F7F for p in pixels)


def test_solid_ignores_brightness_option() -> None:
    from packs.effects.basic.solid import BUILD

    config = EffectConfig(resolution=16, options={"color": 0xFFFFFF, "brightness": 0.5})
    effect = BUILD("basic.solid", config)
    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    # brightness is ignored; raw color is stored as-is
    assert all(p == 0xFFFFFF for p in buf)


# --- Defaults ---


def test_solid_no_color_option_defaults_to_white() -> None:
    from packs.effects.basic.solid import BUILD

    config = EffectConfig(resolution=16)
    effect = BUILD("basic.solid", config)
    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    assert all(p == 0xFFFFFF for p in buf)


# --- Determinism ---


def test_solid_render_is_deterministic() -> None:
    first = _render(color=0x00FF88)
    second = _render(color=0x00FF88)
    assert first == second
