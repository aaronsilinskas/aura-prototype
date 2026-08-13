"""Unit tests for packs.scenes.red_light_green_light.effects.warning_sting."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16, options={})


def _build():
    from packs.scenes.red_light_green_light.effects.warning_sting import BUILD

    return BUILD("scene.warning_sting", _config())


def test_warning_sting_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.red_light_green_light.effects.warning_sting import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_warning_sting_produces_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is not None


def test_warning_sting_emits_audio_on_peak() -> None:
    effect = _build()

    assert "peak" in effect.audio.clips


def test_warning_sting_audio_peak_clip_name_is_scene_prefixed() -> None:
    """Built with the unqualified effect name EffectManager actually passes (see
    EffectManager._build_effect) to prove the clip name is a fixed literal, not
    derived from the builder's `name` argument -- deriving it would produce an
    unprefixed, unresolvable clip name at runtime."""
    from packs.scenes.red_light_green_light.effects.warning_sting import BUILD

    effect = BUILD("warning_sting", _config())

    assert effect.audio.clips["peak"].name == "scene.warning_sting_peak"


def test_warning_sting_audio_peak_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["peak"].loop is False


def test_warning_sting_emits_haptic_on_peak() -> None:
    effect = _build()

    assert "peak" in effect.haptic.patterns
