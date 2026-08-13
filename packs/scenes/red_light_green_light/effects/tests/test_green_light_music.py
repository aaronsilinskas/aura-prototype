"""Unit tests for packs.scenes.red_light_green_light.effects.green_light_music."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.red_light_green_light.effects.green_light_music import BUILD

    return BUILD("scene.green_light_music", _config())


def test_green_light_music_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.red_light_green_light.effects.green_light_music import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_green_light_music_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_green_light_music_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_green_light_music_audio_start_clip_name_is_scene_prefixed() -> None:
    """Built with the unqualified effect name EffectManager actually passes (see
    EffectManager._build_effect) to prove the clip name is a fixed literal, not
    derived from the builder's `name` argument -- deriving it would produce an
    unprefixed, unresolvable clip name at runtime."""
    from packs.scenes.red_light_green_light.effects.green_light_music import BUILD

    effect = BUILD("green_light_music", _config())

    assert effect.audio.clips["start"].name == "scene.green_light_music_start"


def test_green_light_music_audio_start_clip_loops() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is True
