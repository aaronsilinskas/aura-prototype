"""Unit tests for packs.effects.basic.progress."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config(options: dict | None = None) -> EffectConfig:
    return EffectConfig(resolution=16, options=dict(options) if options else {})


def _build(options: dict | None = None):
    from packs.effects.basic.progress import BUILD

    return BUILD("basic.progress", _config(options))


def _render(effect, pixel_count: int = 10) -> list:
    buf = PixelBuffer(pixel_count)
    effect.pixels.render(buf)
    return list(buf)


# --- Builder ---


def test_progress_build_returns_effect_builder_instance() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.effects.basic.progress import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_progress_effect_name_is_basic_progress() -> None:
    effect = _build()
    assert effect.name == "basic.progress"


# --- Rendering: empty and full bars ---


def test_progress_zero_renders_all_dark() -> None:
    pixels = _render(_build(options={"color": 0xFFFFFF, "progress": 0.0}))
    assert all(p == 0x000000 for p in pixels)


def test_progress_full_renders_all_at_color() -> None:
    pixels = _render(_build(options={"color": 0x12AB34, "progress": 1.0}))
    assert all(p == 0x12AB34 for p in pixels)


# --- Rendering: partial bar with anti-aliased boundary ---


def test_progress_partial_lights_region_and_dims_boundary() -> None:
    # 10 pixels, progress 0.55 → 5 full, pixel 5 at half, rest dark.
    pixels = _render(_build(options={"color": 0xFFFFFF, "progress": 0.55}))

    assert all(p == 0xFFFFFF for p in pixels[:5])
    # boundary pixel: int(255 * 0.5) = 127 per channel
    assert pixels[5] == 0x7F7F7F
    assert all(p == 0x000000 for p in pixels[6:])


def test_progress_boundary_scales_color_channels_independently() -> None:
    # color 0xFF8040, boundary fraction 0.5 → int(255*.5),int(128*.5),int(64*.5)
    pixels = _render(_build(options={"color": 0xFF8040, "progress": 0.55}))
    assert pixels[5] == 0x7F4020


# --- Defaults ---


def test_progress_defaults_color_white_and_progress_zero() -> None:
    from packs.effects.basic.progress import BUILD

    effect = BUILD("basic.progress", EffectConfig(resolution=16))
    pixels = _render(effect)
    # default progress 0.0 → all dark
    assert all(p == 0x000000 for p in pixels)


def test_progress_default_color_is_white_when_full() -> None:
    effect = _build(options={"progress": 1.0})
    pixels = _render(effect)
    assert all(p == 0xFFFFFF for p in pixels)


# --- brightness ignored ---


def test_progress_ignores_brightness_option() -> None:
    with_brightness = _build(options={"color": 0xFFFFFF, "progress": 1.0, "brightness": 0.5})
    without_brightness = _build(options={"color": 0xFFFFFF, "progress": 1.0})
    assert _render(with_brightness) == _render(without_brightness)
    assert all(p == 0xFFFFFF for p in _render(without_brightness))


# --- Clamping at build path ---


def test_progress_above_one_renders_all_at_color() -> None:
    pixels = _render(_build(options={"color": 0xFFFFFF, "progress": 1.5}))
    assert all(p == 0xFFFFFF for p in pixels)


def test_progress_below_zero_renders_all_dark() -> None:
    pixels = _render(_build(options={"color": 0xFFFFFF, "progress": -0.5}))
    assert all(p == 0x000000 for p in pixels)


# --- Stateless update ---


def test_progress_update_does_not_change_render() -> None:
    effect = _build(options={"color": 0xFFFFFF, "progress": 0.55})
    before = _render(effect)
    effect.pixels.update(1.0)
    after = _render(effect)
    assert before == after


# --- Determinism ---


def test_progress_render_is_deterministic() -> None:
    first = _render(_build(options={"color": 0x00FF88, "progress": 0.37}))
    second = _render(_build(options={"color": 0x00FF88, "progress": 0.37}))
    assert first == second


# --- Resolvable through the pack registry ---


def test_progress_is_resolvable_via_pack_registry() -> None:
    import os

    from engine.effects.manager import EffectBuilder
    from engine.packs import PackRegistry

    packs_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(os.path.normpath(packs_dir), "packs.effects")

    builder = registry.get("basic", "progress", EffectBuilder)
    effect = builder("basic.progress", _config({"progress": 1.0, "color": 0xFFFFFF}))
    assert effect.name == "basic.progress"
    assert all(p == 0xFFFFFF for p in _render(effect))
