"""Unit tests for packs.scenes.tag.effects.warning_pulse."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer, VibrationConfig
from packs.scenes.tag.effects.warning_pulse import BUILD


def _config(**options) -> EffectConfig:
    return EffectConfig(resolution=16, options=options)


def _build(**options):
    return BUILD("scene.warning_pulse", _config(**options))


def test_warning_pulse_plays_blip_clip_on_peak_event() -> None:
    effect = _build()

    assert effect.audio is not None
    assert effect.audio.clips["peak"].name == "warning_pulse_peak"


def test_warning_pulse_blip_clip_is_one_shot_not_looping() -> None:
    effect = _build()

    assert effect.audio.clips["peak"].loop is False


def test_warning_pulse_buzzes_once_per_pulse_peak() -> None:
    effect = _build()

    assert effect.vibration is not None
    assert effect.vibration.patterns["peak"].sequence == [VibrationConfig.SHARP_CLICK]


def test_warning_pulse_notifies_peak_listener_at_the_pulse_peak() -> None:
    events: list[str] = []
    config = EffectConfig(
        resolution=16,
        options={"brighten_duration": 0.1, "darken_duration": 0.1},
        listeners=[events.append],
    )
    effect = BUILD("scene.warning_pulse", config)

    effect.pixels.update(0.1)

    assert "peak" in events


def test_warning_pulse_renders_configured_end_color_at_peak() -> None:
    effect = _build(
        start_color=0x000000,
        end_color=0xFF00FF,
        brighten_duration=0.1,
        on_duration=0.0,
        darken_duration=0.1,
        off_duration=0.0,
    )

    effect.pixels.update(0.1)  # at the brighten/darken boundary — full end_color
    buf = PixelBuffer(8)
    effect.pixels.render(buf)

    assert all(p == 0xFF00FF for p in buf)
