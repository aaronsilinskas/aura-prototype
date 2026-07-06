import pytest

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectPixels,
    EffectVibration,
    PixelBuffer,
    VibrationConfig,
)

# ---------------------------------------------------------------------------
# EffectConfig — resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = EffectConfig(resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# EffectConfig — get_option
# ---------------------------------------------------------------------------


def test_get_option_returns_stored_value_for_present_key() -> None:
    config = EffectConfig(resolution=10, options={"color": "red"})

    assert config.get_option("color", "blue") == "red"


def test_get_option_returns_default_for_absent_key() -> None:
    config = EffectConfig(resolution=10, options={"color": "red"})

    assert config.get_option("level", 3) == 3


def test_get_option_returns_default_when_no_options_were_provided() -> None:
    config = EffectConfig(resolution=10)

    assert config.get_option("color", "blue") == "blue"


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
# PixelBuffer — capacity vs. logical length
# ---------------------------------------------------------------------------


def test_pixel_buffer_capacity_matches_count_at_construction() -> None:
    buf = PixelBuffer(5)

    assert buf.capacity == 5


def test_resize_shrinks_logical_length_reported_by_len() -> None:
    buf = PixelBuffer(5)

    buf.resize(2)

    assert len(buf) == 2


def test_resize_grows_logical_length_back_toward_capacity() -> None:
    buf = PixelBuffer(5)
    buf.resize(2)

    buf.resize(4)

    assert len(buf) == 4


def test_resize_to_zero_yields_zero_length() -> None:
    buf = PixelBuffer(5)

    buf.resize(0)

    assert len(buf) == 0


def test_resize_above_capacity_raises_value_error() -> None:
    buf = PixelBuffer(5)

    with pytest.raises(ValueError):
        buf.resize(6)


def test_resize_with_negative_count_raises_value_error() -> None:
    buf = PixelBuffer(5)

    with pytest.raises(ValueError):
        buf.resize(-1)


def test_capacity_is_unchanged_after_resize_calls() -> None:
    buf = PixelBuffer(5)

    buf.resize(2)
    buf.resize(5)
    buf.resize(0)

    assert buf.capacity == 5


def test_resize_does_not_reallocate_the_backing_list() -> None:
    buf = PixelBuffer(5)
    backing_list_id = id(buf._pixels)

    buf.resize(2)
    buf.resize(5)

    assert id(buf._pixels) == backing_list_id


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


def test_audio_playback_config_stops_effect_defaults_to_false() -> None:
    cfg = AudioPlaybackConfig(name="sting", loop=False)

    assert cfg.stops_effect is False


def test_audio_playback_config_accepts_stops_effect_true_for_one_shot() -> None:
    cfg = AudioPlaybackConfig(name="sting", loop=False, stops_effect=True)

    assert cfg.stops_effect is True


def test_audio_playback_config_raises_when_loop_and_stops_effect_both_true() -> None:
    with pytest.raises(ValueError):
        AudioPlaybackConfig(name="bg", loop=True, stops_effect=True)


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


# ---------------------------------------------------------------------------
# VibrationConfig — sequence field
# ---------------------------------------------------------------------------


def test_vibration_config_stores_sequence_passed_at_construction() -> None:
    cfg = VibrationConfig(sequence=[VibrationConfig.STRONG_CLICK])

    assert cfg.sequence == [VibrationConfig.STRONG_CLICK]


def test_vibration_config_preserves_multi_step_sequence_in_order() -> None:
    steps = [VibrationConfig.STRONG_CLICK, VibrationConfig.PAUSE_250, VibrationConfig.SOFT_BUMP]
    cfg = VibrationConfig(sequence=steps)

    assert cfg.sequence == steps


# ---------------------------------------------------------------------------
# VibrationConfig — constants do not overlap with DRV2605L hardware IDs
# ---------------------------------------------------------------------------

_DRV2605L_HARDWARE_IDS = {1, 4, 7, 10, 12, 14}
_ALL_VIBRATION_CONSTANTS = [
    VibrationConfig.STRONG_CLICK,
    VibrationConfig.SHARP_CLICK,
    VibrationConfig.SOFT_BUMP,
    VibrationConfig.DOUBLE_CLICK,
    VibrationConfig.TRIPLE_CLICK,
    VibrationConfig.STRONG_BUZZ,
    VibrationConfig.PAUSE_250,
    VibrationConfig.PAUSE_500,
    VibrationConfig.PAUSE_1000,
]


def test_no_vibration_constant_overlaps_with_drv2605l_hardware_waveform_ids() -> None:
    for constant in _ALL_VIBRATION_CONSTANTS:
        assert constant not in _DRV2605L_HARDWARE_IDS, (
            f"VibrationConfig constant {constant} collides with a DRV2605L hardware waveform ID"
        )


# ---------------------------------------------------------------------------
# EffectVibration — typed patterns dict
# ---------------------------------------------------------------------------


def test_effect_vibration_accepts_vibration_config_as_pattern_value() -> None:
    cfg = VibrationConfig(sequence=[VibrationConfig.STRONG_CLICK])
    vibration = EffectVibration(patterns={"cast": cfg})

    assert vibration.patterns["cast"] is cfg
