"""Unit tests for packs.scenes.tag.effects.hit."""

from __future__ import annotations

from effects.effect import EffectConfig, VibrationConfig


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.tag.effects.hit import BUILD

    return BUILD("scene.hit", _config())


def test_hit_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.tag.effects.hit import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_hit_produces_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is not None


def test_hit_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_hit_audio_start_clip_is_one_shot_and_stops_effect() -> None:
    effect = _build()

    clip = effect.audio.clips["start"]
    assert clip.loop is False
    assert clip.stops_effect is True


def test_hit_emits_vibration_on_start() -> None:
    effect = _build()

    assert "start" in effect.vibration.patterns


def test_hit_vibration_start_uses_buzz_pause_click_sequence() -> None:
    effect = _build()

    assert effect.vibration.patterns["start"].sequence == [
        VibrationConfig.STRONG_BUZZ,
        VibrationConfig.PAUSE_250,
        VibrationConfig.STRONG_CLICK,
    ]
