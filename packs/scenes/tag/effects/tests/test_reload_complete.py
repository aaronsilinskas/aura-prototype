"""Unit tests for packs.scenes.tag.effects.reload_complete."""

from __future__ import annotations

from effects.effect import EffectConfig
from packs.scenes.tag.effects.reload_complete import BUILD


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    return BUILD("scene.reload_complete", _config())


def test_reload_complete_has_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_reload_complete_plays_a_one_shot_clip() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "reload_complete"
    assert effect.audio.clips["start"].loop is False


def test_reload_complete_clip_stops_the_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True


def test_reload_complete_emits_haptic() -> None:
    effect = _build()

    assert effect.haptic is not None
    assert "start" in effect.haptic.patterns
