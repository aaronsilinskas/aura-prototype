"""Unit tests for packs.scenes.tag.effects.ready."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer
from packs.scenes.tag.effects.ready import BUILD


def _config() -> EffectConfig:
    return EffectConfig(resolution=16, options={})


def _build():
    return BUILD("scene.ready", _config())


def test_ready_is_dark_at_elapsed_zero() -> None:
    effect = _build()
    effect.pixels.update(0.0)
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0x000000 for p in buf)


def test_ready_pulses_to_a_lit_color() -> None:
    # Mid brighten phase pixels should no longer be black.
    effect = _build()
    effect.pixels.update(0.15)
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert any(p != 0x000000 for p in buf)


def test_ready_has_no_audio() -> None:
    effect = _build()

    assert effect.audio is None
