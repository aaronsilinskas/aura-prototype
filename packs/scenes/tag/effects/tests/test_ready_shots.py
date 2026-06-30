"""Unit tests for packs.scenes.tag.effects.ready_shots."""

from __future__ import annotations

from effects.effect import EffectConfig
from packs.scenes.tag.effects.ready_shots import BUILD


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    return BUILD("scene.ready_shots", _config())


def test_ready_shots_has_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_ready_shots_plays_a_one_shot_clip() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "ready_shots_start"
    assert effect.audio.clips["start"].loop is False
