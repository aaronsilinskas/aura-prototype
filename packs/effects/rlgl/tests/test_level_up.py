"""Unit tests for packs.effects.rlgl.level_up."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, PixelBuffer


def _config() -> EffectConfig:
    return EffectConfig(resolution=16, options={})


def _build() -> Effect:
    from packs.effects.rlgl.level_up import BUILD

    return BUILD("rlgl.level_up", _config())


# --- Pixel output ---


def test_level_up_flash_is_black_before_it_starts() -> None:
    # At elapsed 0.0 the flash has not started — all LEDs are dark
    effect = _build()
    effect.pixels.update(0.0)
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0x000000 for p in buf)


def test_level_up_flash_is_gold_at_peak() -> None:
    # After the brighten phase (0.2 s) all pixels reach full gold (#FFD700)
    effect = _build()
    effect.pixels.update(0.2)  # entering the ON hold phase
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0xFFD700 for p in buf)


def test_level_up_flash_is_uniform_across_all_led_positions() -> None:
    # The gold flash is a whole-strip event — every LED shows the same color
    effect = _build()
    effect.pixels.update(0.3)  # mid-ON phase
    buf = PixelBuffer(16)
    effect.pixels.render(buf)

    first = buf[0]
    assert all(p == first for p in buf)


# --- Audio ---


def test_level_up_plays_level_up_start_clip_on_start_event() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["start"].name == "level_up_start"


def test_level_up_audio_clip_is_one_shot_not_looping() -> None:
    effect = _build()

    assert effect.audio.clips["start"].loop is False


# --- Vibration ---


def test_level_up_triggers_double_click_haptic_on_start_event() -> None:
    from effects.effect import VibrationConfig

    effect = _build()

    assert effect.vibration is not None
    assert effect.vibration.patterns["start"].sequence == [VibrationConfig.DOUBLE_CLICK]
