"""Unit tests for packs.scenes.tag.effects.reload."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer
from packs.scenes.tag.effects.reload import BUILD


def _config(**options) -> EffectConfig:
    return EffectConfig(resolution=16, options=options)


def _build(**options):
    return BUILD("scene.reload", _config(**options))


def test_reload_has_pixel_output() -> None:
    effect = _build(duration=2.0)

    assert effect.pixels is not None


def test_reload_renders_no_fill_before_any_update() -> None:
    effect = _build(duration=2.0)

    buf = PixelBuffer(4)
    effect.pixels.render(buf)

    assert all(p == 0x000000 for p in buf)


def test_reload_fills_proportionally_to_elapsed_over_duration_option() -> None:
    effect = _build(duration=2.0, color=0xFFFFFF)

    effect.pixels.update(1.0)  # halfway through the 2.0s duration -> progress 0.5

    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    assert list(buf) == [0xFFFFFF, 0xFFFFFF, 0x000000, 0x000000]


def test_reload_defaults_to_red_fill_when_no_color_option_given() -> None:
    effect = _build(duration=2.0)

    effect.pixels.update(1.0)  # halfway through the 2.0s duration -> progress 0.5

    buf = PixelBuffer(4)
    effect.pixels.render(buf)
    assert list(buf) == [0xFF0000, 0xFF0000, 0x000000, 0x000000]


def test_reload_plays_a_looping_reload_clip() -> None:
    effect = _build(duration=2.0)

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "reload"
    assert effect.audio.clips["start"].loop is True
