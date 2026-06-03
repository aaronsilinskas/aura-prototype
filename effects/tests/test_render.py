import pytest

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectPixels,
    EffectVibration,
    PixelBuffer,
)

# ---------------------------------------------------------------------------
# EffectConfig — resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = EffectConfig(resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# EffectConfig — options
# ---------------------------------------------------------------------------


def test_config_preserves_options_dict_passed_at_construction() -> None:
    opts = {"color": "red"}
    config = EffectConfig(resolution=10, options=opts)

    assert config.options == opts


def test_config_options_defaults_to_empty_dict() -> None:
    config = EffectConfig(resolution=10)

    assert config.options == {}


# ---------------------------------------------------------------------------
# EffectConfig — listeners
# ---------------------------------------------------------------------------


def test_notify_listeners_is_silent_when_no_listeners_are_registered() -> None:
    config = EffectConfig(resolution=10)

    config.notify_listeners("frame_start")  # must not raise


def test_registered_listener_receives_event_on_notify() -> None:
    received: list[str] = []
    config = EffectConfig(
        resolution=10,
        listeners=[received.append],
    )

    config.notify_listeners("frame_start")

    assert received == ["frame_start"]


def test_all_registered_listeners_are_notified_in_registration_order() -> None:
    received: list[str] = []
    config = EffectConfig(
        resolution=10,
        listeners=[
            lambda e: received.append(f"a:{e}"),
            lambda e: received.append(f"b:{e}"),
        ],
    )

    config.notify_listeners("tick")

    assert received == ["a:tick", "b:tick"]


# ---------------------------------------------------------------------------
# PixelBuffer
# ---------------------------------------------------------------------------


def test_pixel_buffer_count_matches_size_at_construction() -> None:
    buf = PixelBuffer(5)

    assert len(buf) == 5


def test_pixel_buffer_initializes_all_pixels_to_zero() -> None:
    buf = PixelBuffer(4)

    assert list(buf) == [0, 0, 0, 0]


def test_pixel_buffer_setitem_stores_color_at_given_index() -> None:
    buf = PixelBuffer(3)

    buf[1] = 0xFF0000

    assert buf[1] == 0xFF0000


def test_pixel_buffer_iterates_pixels_in_index_order() -> None:
    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    assert list(buf) == [0xFF0000, 0x00FF00, 0x0000FF]


# ---------------------------------------------------------------------------
# Effect — capability container
# ---------------------------------------------------------------------------


def test_effect_stores_name_passed_at_construction() -> None:
    effect = Effect(name="elements.fire")

    assert effect.name == "elements.fire"


def test_effect_pixels_defaults_to_none() -> None:
    effect = Effect(name="test")

    assert effect.pixels is None


def test_effect_stores_pixels_passed_at_construction() -> None:
    class _FakePixels(EffectPixels):
        def update(self, elapsed: float) -> None:
            pass

        def render(self, output: PixelBuffer) -> None:
            pass

    pixels = _FakePixels()
    effect = Effect(name="test", pixels=pixels)

    assert effect.pixels is pixels


def test_effect_audio_defaults_to_none() -> None:
    effect = Effect(name="test")

    assert effect.audio is None


def test_effect_vibration_defaults_to_none() -> None:
    effect = Effect(name="test")

    assert effect.vibration is None


def test_effect_stores_audio_and_vibration_passed_at_construction() -> None:
    audio = EffectAudio(clips={})
    vibration = EffectVibration(patterns={})
    effect = Effect(name="test", audio=audio, vibration=vibration)

    assert effect.audio is audio
    assert effect.vibration is vibration


# ---------------------------------------------------------------------------
# EffectPixels — abstract base class protocol
# ---------------------------------------------------------------------------


def test_effect_pixels_update_raises_not_implemented() -> None:
    pixels = EffectPixels()
    with pytest.raises(NotImplementedError):
        pixels.update(0.016)


def test_effect_pixels_render_raises_not_implemented() -> None:
    pixels = EffectPixels()
    with pytest.raises(NotImplementedError):
        pixels.render(PixelBuffer(1))


# ---------------------------------------------------------------------------
# AudioPlaybackConfig — fields
# ---------------------------------------------------------------------------


def test_audio_playback_config_stores_name_and_loop() -> None:
    cfg = AudioPlaybackConfig(name="red_light_music", loop=True)

    assert cfg.name == "red_light_music"
    assert cfg.loop is True


def test_audio_playback_config_stores_one_shot_loop_false() -> None:
    cfg = AudioPlaybackConfig(name="sting", loop=False)

    assert cfg.loop is False


# ---------------------------------------------------------------------------
# EffectAudio — clips
# ---------------------------------------------------------------------------


def test_effect_audio_stores_clips_dict() -> None:
    clip = AudioPlaybackConfig(name="bg", loop=True)
    audio = EffectAudio(clips={"start": clip})

    assert audio.clips["start"] is clip


# ---------------------------------------------------------------------------
# EffectVibration — patterns
# ---------------------------------------------------------------------------


def test_effect_vibration_stores_patterns_dict() -> None:
    vibration = EffectVibration(patterns={"strike": object()})

    assert "strike" in vibration.patterns
