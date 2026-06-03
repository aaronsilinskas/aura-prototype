import pytest

from effects.effect import Effect, EffectConfig, PixelBuffer

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
# Effect — base class protocol
# ---------------------------------------------------------------------------


def test_base_effect_name_raises_not_implemented() -> None:
    effect = Effect()
    with pytest.raises(NotImplementedError):
        _ = effect.name


def test_base_effect_update_raises_not_implemented() -> None:
    effect = Effect()
    with pytest.raises(NotImplementedError):
        effect.update(0.016)


def test_base_effect_render_raises_not_implemented() -> None:
    effect = Effect()
    with pytest.raises(NotImplementedError):
        effect.render(PixelBuffer(1))
