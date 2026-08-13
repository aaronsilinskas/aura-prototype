"""Unit tests for packs.scenes.red_light_green_light.effects.game_over_sting."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.red_light_green_light.effects.game_over_sting import BUILD

    return BUILD("scene.game_over_sting", _config())


def test_game_over_sting_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.red_light_green_light.effects.game_over_sting import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_game_over_sting_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_game_over_sting_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_game_over_sting_audio_start_clip_name_points_at_shared_basic_clip() -> None:
    """rlgl's game_over_sting reuses basic's shared sting rather than shipping its own.

    Built with the unqualified effect name EffectManager actually passes (see
    EffectManager._build_effect) to prove the clip name is a fixed literal, not
    derived from the builder's `name` argument -- deriving it would produce an
    unprefixed, unresolvable clip name at runtime.
    """
    from packs.scenes.red_light_green_light.effects.game_over_sting import BUILD

    effect = BUILD("game_over_sting", _config())

    assert effect.audio.clips["start"].name == "basic.game_over_sting_start"


def test_game_over_sting_audio_start_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_game_over_sting_emits_haptic_on_start() -> None:
    effect = _build()

    assert "start" in effect.haptic.patterns


def test_game_over_sting_haptic_start_uses_strong_buzz() -> None:
    from effects.effect import HapticPattern

    effect = _build()

    assert HapticPattern.STRONG_BUZZ in effect.haptic.patterns["start"].sequence
