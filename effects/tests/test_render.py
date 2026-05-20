from effects.effect import Effect, EffectState
from effects.palette import Palette, PaletteLUT256
from effects.render import (
    EffectRenderer,
    MergeRenderer,
    PixelBuffer,
    RendererConfig,
)
from effects.tests.helpers import CountUpdates, make_timer

# ---------------------------------------------------------------------------
# RendererConfig — level clamping
# ---------------------------------------------------------------------------


def test_config_clamps_level_below_one_to_one() -> None:
    config = RendererConfig(level=0, resolution=10)

    assert config.level == 1


def test_config_clamps_level_above_ten_to_ten() -> None:
    config = RendererConfig(level=11, resolution=10)

    assert config.level == 10


def test_config_stores_level_within_valid_range_unchanged() -> None:
    config = RendererConfig(level=5, resolution=10)

    assert config.level == 5


def test_config_stores_options_dict() -> None:
    opts = {"color": "red"}
    config = RendererConfig(level=5, resolution=10, options=opts)

    assert config.options == opts


def test_config_options_defaults_to_empty_dict() -> None:
    config = RendererConfig(level=5, resolution=10)

    assert config.options == {}


# ---------------------------------------------------------------------------
# RendererConfig — resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = RendererConfig(level=5, resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# RendererConfig — listeners
# ---------------------------------------------------------------------------


def test_notify_listeners_is_silent_when_no_listeners_are_registered() -> None:
    config = RendererConfig(level=5, resolution=10)

    config.notify_listeners("frame_start")  # must not raise


def test_registered_listener_receives_event_on_notify() -> None:
    received: list[str] = []
    config = RendererConfig(
        level=5,
        resolution=10,
        listeners=[received.append],
    )

    config.notify_listeners("frame_start")

    assert received == ["frame_start"]


def test_all_registered_listeners_are_notified_in_registration_order() -> None:
    received: list[str] = []
    config = RendererConfig(
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
# RendererConfig — level_lerp
# ---------------------------------------------------------------------------


def test_config_level_lerp_returns_minimum_at_level_one() -> None:
    config = RendererConfig(level=1, resolution=10)

    assert config.level_lerp(0.2, 1.0) == 0.2


def test_config_level_lerp_returns_maximum_at_level_ten() -> None:
    config = RendererConfig(level=10, resolution=10)

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
# EffectRenderer — render pipeline
# ---------------------------------------------------------------------------


def test_renderer_exposes_effect_name() -> None:
    renderer = EffectRenderer(
        Effect("my_effect"), PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    )

    assert renderer.name == "my_effect"


def test_renderer_maps_effect_value_through_palette_to_produce_packed_color() -> None:
    # Effect always returns 1.0; black→red palette maps 1.0 to full red.
    effect = Effect("test", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    output = PixelBuffer(1)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(255, 0, 0)


def test_renderer_returns_black_when_effect_value_is_zero() -> None:
    effect = Effect("test", lambda _: 0.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))  # black → red
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    output = PixelBuffer(1)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(0, 0, 0)


def test_renderer_update_propagates_to_effect_step() -> None:
    counter = CountUpdates()
    effect = Effect("test", lambda _: 0.0).add_steps([counter])
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    renderer.update(state, make_timer(0.016))
    renderer.update(state, make_timer(0.016))

    assert counter.count == 2


def test_renderer_fills_all_pixels_in_output() -> None:
    effect = Effect("test", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    output = PixelBuffer(3)
    renderer.render(state, output)

    assert list(output) == [Palette.pack_rgb(255, 0, 0)] * 3


def test_renderer_samples_each_pixel_at_its_normalized_position() -> None:
    # Effect returns 0.0 for position < 0.5, 1.0 otherwise.
    # pixel[0] → position 0/2 = 0.0 → black; pixel[1] → position 1/2 = 0.5 → red.
    effect = Effect("test", lambda pos: 1.0 if pos >= 0.5 else 0.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    output = PixelBuffer(2)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(0, 0, 0)
    assert output[1] == Palette.pack_rgb(255, 0, 0)


# ---------------------------------------------------------------------------
# MergeRenderer — name
# ---------------------------------------------------------------------------


def test_merge_renderer_name_returns_name_passed_at_construction() -> None:
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    renderer = MergeRenderer("my_merge", [EffectRenderer(Effect("e"), palette)])

    assert renderer.name == "my_merge"


# ---------------------------------------------------------------------------
# MergeRenderer — average (default)
# ---------------------------------------------------------------------------


def test_merge_renderer_with_single_renderer_produces_same_color() -> None:
    effect = Effect("test", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))  # black → red
    state = EffectState()
    single = EffectRenderer(effect, palette)
    merged = MergeRenderer("test", [EffectRenderer(effect, palette)])

    out_merged = PixelBuffer(1)
    out_single = PixelBuffer(1)
    merged.render(state, out_merged)
    single.render(state, out_single)

    assert out_merged[0] == out_single[0]


def test_merge_renderer_averages_rgb_channels_across_renderers() -> None:
    # Renderer A → full red (255,0,0); Renderer B → full blue (0,0,255).
    # Average: r=(255+0)//2=127, g=0, b=(0+255)//2=127.
    red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    blue_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 0, 255]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect, red_palette),
            EffectRenderer(effect, blue_palette),
        ],
    )

    output = PixelBuffer(1)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(127, 0, 127)


def test_merge_renderer_update_propagates_to_all_child_renderers() -> None:
    counter_a = CountUpdates()
    counter_b = CountUpdates()
    effect_a = Effect("a", lambda _: 0.0).add_steps([counter_a])
    effect_b = Effect("b", lambda _: 0.0).add_steps([counter_b])
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect_a, palette),
            EffectRenderer(effect_b, palette),
        ],
    )

    renderer.update(state, make_timer(0.016))

    assert counter_a.count == 1
    assert counter_b.count == 1


def test_merge_renderer_average_renders_each_pixel_independently() -> None:
    # Effect A: full red at position >= 0.5, black otherwise.
    # Effect B: always full blue.
    # pixel[0] (pos=0.0): A=black, B=blue  → average = (0, 0, 127)
    # pixel[1] (pos=0.5): A=red,   B=blue  → average = (127, 0, 127)
    effect_a = Effect("a", lambda pos: 1.0 if pos >= 0.5 else 0.0)
    effect_b = Effect("b", lambda _: 1.0)
    red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    blue_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 0, 255]))
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect_a, red_palette),
            EffectRenderer(effect_b, blue_palette),
        ],
    )

    output = PixelBuffer(2)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(0, 0, 127)
    assert output[1] == Palette.pack_rgb(127, 0, 127)


# ---------------------------------------------------------------------------
# MergeRenderer — additive
# ---------------------------------------------------------------------------


def test_merge_renderer_additive_sums_rgb_channels_across_renderers() -> None:
    # Each renderer produces r=64; two renderers → r=128.
    dim_red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 64, 0, 0]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect, dim_red_palette),
            EffectRenderer(effect, dim_red_palette),
        ],
        additive=True,
    )

    output = PixelBuffer(1)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(128, 0, 0)


def test_merge_renderer_additive_clamps_channel_to_255_on_overflow() -> None:
    # Each renderer produces g=128; sum=256 → clamped to 255.
    green_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 128, 0]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect, green_palette),
            EffectRenderer(effect, green_palette),
        ],
        additive=True,
    )

    output = PixelBuffer(1)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(0, 255, 0)


def test_merge_renderer_additive_renders_each_pixel_independently() -> None:
    # Effect A: full red at position >= 0.5, black otherwise.
    # Effect B: always dim blue (0, 0, 64).
    # pixel[0] (pos=0.0): A=black,    B=dim_blue → sum = (0, 0, 64)
    # pixel[1] (pos=0.5): A=full_red, B=dim_blue → sum = (255, 0, 64)
    effect_a = Effect("a", lambda pos: 1.0 if pos >= 0.5 else 0.0)
    effect_b = Effect("b", lambda _: 1.0)
    red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    dim_blue_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 0, 64]))
    state = EffectState()
    renderer = MergeRenderer(
        "test",
        [
            EffectRenderer(effect_a, red_palette),
            EffectRenderer(effect_b, dim_blue_palette),
        ],
        additive=True,
    )

    output = PixelBuffer(2)
    renderer.render(state, output)

    assert output[0] == Palette.pack_rgb(0, 0, 64)
    assert output[1] == Palette.pack_rgb(255, 0, 64)
