"""Tests for rlgl audio effect builders."""

from __future__ import annotations

from effects.effect import EffectAudio, EffectConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16, options={}, listeners=[])


# ---------------------------------------------------------------------------
# red_light_music
# ---------------------------------------------------------------------------


def test_red_light_music_build_returns_effect_with_loop_audio() -> None:
    from packs.effects.rlgl.red_light_music import BUILD

    effect = BUILD("red_light_music", _config())
    assert effect.name == "red_light_music"
    assert effect.pixels is None
    assert isinstance(effect.audio, EffectAudio)
    config = effect.audio.clips["start"]
    assert config.name == "red_light_music_start"
    assert config.loop is True


# ---------------------------------------------------------------------------
# green_light_music
# ---------------------------------------------------------------------------


def test_green_light_music_build_returns_effect_with_loop_audio() -> None:
    from packs.effects.rlgl.green_light_music import BUILD

    effect = BUILD("green_light_music", _config())
    assert effect.name == "green_light_music"
    assert effect.pixels is None
    assert isinstance(effect.audio, EffectAudio)
    config = effect.audio.clips["start"]
    assert config.name == "green_light_music_start"
    assert config.loop is True


# ---------------------------------------------------------------------------
# game_over_sting
# ---------------------------------------------------------------------------


def test_game_over_sting_build_returns_effect_with_oneshot_audio() -> None:
    from packs.effects.rlgl.game_over_sting import BUILD

    effect = BUILD("game_over_sting", _config())
    assert effect.name == "game_over_sting"
    assert effect.pixels is None
    assert isinstance(effect.audio, EffectAudio)
    config = effect.audio.clips["start"]
    assert config.name == "game_over_sting_start"
    assert config.loop is False


# ---------------------------------------------------------------------------
# warning_sting — pixels + audio
# ---------------------------------------------------------------------------


def test_warning_sting_build_has_both_pixels_and_audio() -> None:
    from packs.effects.rlgl.warning_sting import BUILD

    effect = BUILD("warning_sting", _config())
    assert effect.name == "warning_sting"
    assert effect.pixels is not None
    assert isinstance(effect.audio, EffectAudio)
    config = effect.audio.clips["peak"]
    assert config.name == "warning_sting_peak"
    assert config.loop is False


# ---------------------------------------------------------------------------
# ready — pixels + audio
# ---------------------------------------------------------------------------


def test_ready_build_has_both_pixels_and_audio() -> None:
    from packs.effects.rlgl.ready import BUILD

    effect = BUILD("ready", _config())
    assert effect.name == "ready"
    assert effect.pixels is not None
    assert isinstance(effect.audio, EffectAudio)
    config = effect.audio.clips["start"]
    assert config.name == "ready_start"
    assert config.loop is False
