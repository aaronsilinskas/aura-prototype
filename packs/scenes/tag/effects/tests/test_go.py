"""Unit tests for packs.scenes.tag.effects.go."""

from __future__ import annotations

from effects.effect import EffectConfig, HapticPattern
from packs.scenes.tag.effects.go import BUILD


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    return BUILD("scene.go", _config())


def test_go_has_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_go_plays_a_one_shot_clip() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "scene.go_start"
    assert effect.audio.clips["start"].loop is False


def test_go_clip_stops_the_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True


def test_go_buzzes_strongly_on_start() -> None:
    effect = _build()

    assert effect.haptic is not None
    assert effect.haptic.patterns["start"].sequence == [HapticPattern.STRONG_BUZZ]
