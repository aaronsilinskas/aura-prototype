import pytest

from effects.render import Effect, EffectConfig, PixelBuffer

# ---------------------------------------------------------------------------
# EffectConfig — level clamping
# ---------------------------------------------------------------------------


def test_config_clamps_level_below_one_to_one() -> None:
    config = EffectConfig(level=0, resolution=10)

    assert config.level == 1


def test_config_clamps_level_above_ten_to_ten() -> None:
    config = EffectConfig(level=11, resolution=10)

    assert config.level == 10


def test_config_stores_level_within_valid_range_unchanged() -> None:
    config = EffectConfig(level=5, resolution=10)

    assert config.level == 5


def test_config_preserves_options_dict_passed_at_construction() -> None:
    opts = {"color": "red"}
    config = EffectConfig(level=5, resolution=10, options=opts)

    assert config.options == opts


def test_config_options_defaults_to_empty_dict() -> None:
    config = EffectConfig(level=5, resolution=10)

    assert config.options == {}


# ---------------------------------------------------------------------------
# EffectConfig — resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = EffectConfig(level=5, resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# EffectConfig — listeners
# ---------------------------------------------------------------------------


def test_notify_listeners_is_silent_when_no_listeners_are_registered() -> None:
    config = EffectConfig(level=5, resolution=10)

    config.notify_listeners("frame_start")  # must not raise


def test_registered_listener_receives_event_on_notify() -> None:
    received: list[str] = []
    config = EffectConfig(
        level=5,
        resolution=10,
        listeners=[received.append],
    )

    config.notify_listeners("frame_start")

    assert received == ["frame_start"]


def test_all_registered_listeners_are_notified_in_registration_order() -> None:
    received: list[str] = []
    config = EffectConfig(
        level=5,
        resolution=10,
        listeners=[
            lambda e: received.append(f"a:{e}"),
            lambda e: received.append(f"b:{e}"),
        ],
    )

    config.notify_listeners("tick")

    assert received == ["a:tick", "b:tick"]


# ---------------------------------------------------------------------------
# EffectConfig — level_lerp
# ---------------------------------------------------------------------------


def test_config_level_lerp_returns_minimum_at_level_one() -> None:
    config = EffectConfig(level=1, resolution=10)

    assert config.level_lerp(0.2, 1.0) == 0.2


def test_config_level_lerp_returns_maximum_at_level_ten() -> None:
    config = EffectConfig(level=10, resolution=10)

    assert config.level_lerp(0.2, 1.0) == 1.0


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
# Effect — base class protocol
# ---------------------------------------------------------------------------


def test_base_renderer_name_raises_not_implemented() -> None:
    renderer = Effect()
    with pytest.raises(NotImplementedError):
        _ = renderer.name


def test_base_renderer_update_raises_not_implemented() -> None:
    renderer = Effect()
    with pytest.raises(NotImplementedError):
        renderer.update(0.016)


def test_base_renderer_render_raises_not_implemented() -> None:
    renderer = Effect()
    with pytest.raises(NotImplementedError):
        renderer.render(PixelBuffer(1))
