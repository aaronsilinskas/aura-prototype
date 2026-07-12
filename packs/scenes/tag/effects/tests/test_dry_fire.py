"""Unit tests for packs.scenes.tag.effects.dry_fire."""

from __future__ import annotations

from effects.effect import EffectConfig, HapticPattern
from packs.scenes.tag.effects.dry_fire import BUILD


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    return BUILD("scene.dry_fire", _config())


def test_dry_fire_has_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_dry_fire_plays_a_one_shot_clip() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "dry_fire_start"
    assert effect.audio.clips["start"].loop is False


def test_dry_fire_clip_stops_the_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True


def test_dry_fire_emits_a_soft_haptic_bump() -> None:
    effect = _build()

    assert effect.haptic is not None
    assert effect.haptic.patterns["start"].sequence == [HapticPattern.SOFT_BUMP]
