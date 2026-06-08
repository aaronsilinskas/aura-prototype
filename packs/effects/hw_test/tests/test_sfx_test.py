"""Unit tests for packs.effects.hw_test.sfx_test."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.effects.hw_test.sfx_test import BUILD

    return BUILD("hw_test.sfx_test", _config())


def test_sfx_test_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.effects.hw_test.sfx_test import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_sfx_test_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_sfx_test_plays_audio_on_start() -> None:
    effect = _build()

    assert effect.audio is not None
    assert "start" in effect.audio.clips


def test_sfx_test_audio_start_clip_name_is_sfx_test_start() -> None:
    effect = _build()

    assert effect.audio.clips["start"].name == "sfx_test_start"


def test_sfx_test_audio_start_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_sfx_test_triggers_vibration_on_start() -> None:
    effect = _build()

    assert effect.vibration is not None
    assert "start" in effect.vibration.patterns


def test_sfx_test_vibration_start_pattern_is_strong_click() -> None:
    from effects.effect import VibrationConfig

    effect = _build()

    assert effect.vibration.patterns["start"].sequence == [VibrationConfig.STRONG_CLICK]
