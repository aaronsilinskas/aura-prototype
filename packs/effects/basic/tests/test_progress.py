"""Unit tests for packs.effects.basic.progress.

Pixel mapping is covered by ``effects/tests/layers/test_progress_renderer.py``;
these check only the builder's options.
"""

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
    from engine.effects.builder import EffectBuilder
    from packs.effects.basic.progress import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_progress_effect_name_is_basic_progress() -> None:
    effect = _build()
    assert effect.name == "basic.progress"


# --- color option ---


def test_progress_color_option_sets_fill_color() -> None:
    pixels = _render(_build(options={"color": 0x12AB34, "progress": 1.0}))
    assert all(p == 0x12AB34 for p in pixels)


def test_progress_default_color_is_white() -> None:
    pixels = _render(_build(options={"progress": 1.0}))
    assert all(p == 0xFFFFFF for p in pixels)


# --- progress option ---


def test_progress_option_sets_how_far_the_fill_reaches() -> None:
    pixels = _render(_build(options={"color": 0xFFFFFF, "progress": 0.3}))
    assert pixels == [0xFFFFFF] * 3 + [0x000000] * 7


def test_progress_default_progress_is_empty() -> None:
    pixels = _render(_build(options={"color": 0xFFFFFF}))
    assert all(p == 0x000000 for p in pixels)


# --- brightness ignored ---


def test_progress_ignores_brightness_option() -> None:
    with_brightness = _build(options={"color": 0xFFFFFF, "progress": 1.0, "brightness": 0.5})
    assert all(p == 0xFFFFFF for p in _render(with_brightness))


# --- Resolvable through the pack registry ---


def test_progress_is_resolvable_via_pack_registry() -> None:
    import os

    from engine.effects.builder import EffectBuilder
    from engine.pack_catalog import scan_pack_roots

    packs_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    registry = scan_pack_roots([os.path.normpath(packs_root)]).effect_registry

    builder = registry.get("basic", "progress", EffectBuilder)
    effect = builder("basic.progress", _config({"progress": 1.0, "color": 0xFFFFFF}))
    assert effect.name == "basic.progress"
    assert all(p == 0xFFFFFF for p in _render(effect))
