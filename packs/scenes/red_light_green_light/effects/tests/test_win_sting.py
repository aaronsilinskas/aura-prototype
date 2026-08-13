"""Unit tests for packs.scenes.red_light_green_light.effects.win_sting."""

from __future__ import annotations

from effects.effect import EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.red_light_green_light.effects.win_sting import BUILD

    return BUILD("scene.win_sting", _config())


def test_win_sting_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.red_light_green_light.effects.win_sting import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_win_sting_produces_no_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is None


def test_win_sting_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_win_sting_audio_start_clip_name_is_scene_prefixed() -> None:
    effect = _build()

    assert effect.audio.clips["start"].name == "scene.win_sting_start"


def test_win_sting_audio_start_clip_is_non_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_win_sting_emits_haptic_on_start() -> None:
    effect = _build()

    assert "start" in effect.haptic.patterns


def test_win_sting_haptic_pattern_is_distinct_from_game_over_sting() -> None:
    from packs.scenes.red_light_green_light.effects.game_over_sting import BUILD as GAME_OVER_BUILD

    win_effect = _build()
    game_over_effect = GAME_OVER_BUILD("scene.game_over_sting", _config())

    win_pattern = win_effect.haptic.patterns["start"].sequence
    game_over_pattern = game_over_effect.haptic.patterns["start"].sequence

    assert win_pattern != game_over_pattern


def test_win_sting_haptic_start_uses_triple_click() -> None:
    from effects.effect import HapticPattern

    effect = _build()

    assert HapticPattern.TRIPLE_CLICK in effect.haptic.patterns["start"].sequence


def test_win_sting_audio_start_clip_stops_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True
