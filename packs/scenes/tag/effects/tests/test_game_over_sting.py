"""Unit tests for packs.scenes.tag.effects.game_over_sting."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.tag.effects.game_over_sting import BUILD

    return BUILD("scene.game_over_sting", _config())


def test_game_over_sting_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.tag.effects.game_over_sting import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_game_over_sting_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_game_over_sting_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_game_over_sting_audio_start_clip_name_points_at_shared_basic_clip() -> None:
    """tag's game_over_sting reuses basic's shared sting rather than shipping its own."""
    effect = _build()

    assert effect.audio.clips["start"].name == "basic.game_over_sting_start"


def test_game_over_sting_audio_start_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_game_over_sting_audio_start_clip_stops_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True


def test_game_over_sting_emits_haptic_on_start() -> None:
    effect = _build()

    assert "start" in effect.haptic.patterns


def test_game_over_sting_haptic_start_uses_strong_buzz() -> None:
    from effects.effect import HapticPattern

    effect = _build()

    assert HapticPattern.STRONG_BUZZ in effect.haptic.patterns["start"].sequence
