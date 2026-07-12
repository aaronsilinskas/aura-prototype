"""Unit tests for packs.scenes.hardware_test.effects.sfx_test."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.hardware_test.effects.sfx_test import BUILD

    return BUILD("sfx_test", _config())


def test_sfx_test_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.hardware_test.effects.sfx_test import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_sfx_test_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_sfx_test_has_audio_capability() -> None:
    effect = _build()

    assert effect.audio is not None


def test_sfx_test_audio_responds_to_start_verb() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_sfx_test_audio_start_clip_name_is_sfx_test_start() -> None:
    effect = _build()

    assert effect.audio.clips["start"].name == "sfx_test_start"


def test_sfx_test_audio_start_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_sfx_test_has_haptic_capability() -> None:
    effect = _build()

    assert effect.haptic is not None


def test_sfx_test_haptic_responds_to_start_verb() -> None:
    effect = _build()

    assert "start" in effect.haptic.patterns


def test_sfx_test_haptic_start_pattern_is_strong_click() -> None:
    from effects.effect import HapticPattern

    effect = _build()

    assert effect.haptic.patterns["start"].sequence == [HapticPattern.STRONG_CLICK]
