"""Unit tests for packs.scenes.tag.effects.fire_shot."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer


def _config() -> EffectConfig:
    return EffectConfig(resolution=16)


def _build():
    from packs.scenes.tag.effects.fire_shot import BUILD

    return BUILD("scene.fire_shot", _config())


def test_fire_shot_build_is_effect_builder() -> None:
    from engine.effects.manager import EffectBuilder
    from packs.scenes.tag.effects.fire_shot import BUILD

    assert isinstance(BUILD, EffectBuilder)


def test_fire_shot_has_pixel_output() -> None:
    effect = _build()

    assert effect.pixels is not None


def test_fire_shot_renders_a_visible_flash() -> None:
    effect = _build()

    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert any(p != 0 for p in buf)


def test_fire_shot_emits_audio_on_start() -> None:
    effect = _build()

    assert "start" in effect.audio.clips


def test_fire_shot_audio_start_clip_is_one_shot_not_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


def test_fire_shot_audio_start_clip_stops_effect() -> None:
    effect = _build()

    assert effect.audio.clips["start"].stops_effect is True


def test_fire_shot_emits_vibration_on_start() -> None:
    effect = _build()

    assert "start" in effect.vibration.patterns


def test_fire_shot_vibration_start_uses_sharp_click() -> None:
    from effects.effect import VibrationConfig

    effect = _build()

    assert VibrationConfig.SHARP_CLICK in effect.vibration.patterns["start"].sequence
