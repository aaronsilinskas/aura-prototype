"""Unit tests for packs.scenes.rlgl.effects.level_up."""

from __future__ import annotations

from effects.effect import Effect, EffectConfig, PixelBuffer


def _config() -> EffectConfig:
    return EffectConfig(resolution=16, options={})


def _build() -> Effect:
    from packs.scenes.rlgl.effects.level_up import BUILD

    return BUILD("scene.level_up", _config())


# --- Pixel output ---


def test_level_up_flash_starts_dark_at_elapsed_zero() -> None:
    # At elapsed 0.0 the brighten ramp has not advanced — all LEDs are dark
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


def test_level_up_flash_dims_during_darken_phase() -> None:
    # Mid-darken (t=0.75): frac = 1.0 - (0.75-0.6)/0.3 = 0.5 — pixels are
    # partially lit: not black and not at peak gold
    effect = _build()
    effect.pixels.update(0.75)
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p != 0x000000 and p != 0xFFD700 for p in buf)


def test_level_up_flash_is_dark_during_off_phase() -> None:
    # At t=0.95 (off phase, after darken ends at 0.9) the strip is dark again
    effect = _build()
    effect.pixels.update(0.95)
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0x000000 for p in buf)


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
