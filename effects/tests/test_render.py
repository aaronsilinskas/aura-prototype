from effects.effect import Effect, EffectState
from effects.palette import Palette, PaletteLUT256
from effects.render import (
    AdditiveMergeRenderer,
    AverageMergeRenderer,
    EffectRenderer,
    RendererConfig,
)
from effects.tests.helpers import CountUpdates, make_timer

# ---------------------------------------------------------------------------
# RendererConfig — level clamping
# ---------------------------------------------------------------------------


def test_config_clamps_level_below_one_to_one() -> None:
    config = RendererConfig(level=0, pixel_count=10, resolution=10)

    assert config.level == 1


def test_config_clamps_level_above_ten_to_ten() -> None:
    config = RendererConfig(level=11, pixel_count=10, resolution=10)

    assert config.level == 10


def test_config_stores_level_within_valid_range_unchanged() -> None:
    config = RendererConfig(level=5, pixel_count=10, resolution=10)

    assert config.level == 5


def test_config_stores_options_dict() -> None:
    opts = {"color": "red"}
    config = RendererConfig(level=5, pixel_count=10, resolution=10, options=opts)

    assert config.options == opts


def test_config_options_defaults_to_empty_dict() -> None:
    config = RendererConfig(level=5, pixel_count=10, resolution=10)

    assert config.options == {}


# ---------------------------------------------------------------------------
# RendererConfig — pixel_count and resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_pixel_count_below_one_to_one() -> None:
    config = RendererConfig(level=5, pixel_count=0, resolution=10)

    assert config.pixel_count == 1


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = RendererConfig(level=5, pixel_count=10, resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# RendererConfig — listeners
# ---------------------------------------------------------------------------


def test_notify_listeners_is_silent_when_no_listeners_are_registered() -> None:
    config = RendererConfig(level=5, pixel_count=10, resolution=10)

    config.notify_listeners("frame_start")  # must not raise


def test_registered_listener_receives_event_on_notify() -> None:
    received: list[str] = []
    config = RendererConfig(
        level=5,
        pixel_count=10,
        resolution=10,
        listeners=[received.append],
    )

    config.notify_listeners("frame_start")

    assert received == ["frame_start"]


def test_all_registered_listeners_are_notified_in_registration_order() -> None:
    received: list[str] = []
    config = RendererConfig(
        level=5,
        pixel_count=10,
        resolution=10,
        listeners=[
            lambda e: received.append(f"a:{e}"),
            lambda e: received.append(f"b:{e}"),
        ],
    )

    config.notify_listeners("tick")

    assert received == ["a:tick", "b:tick"]


# ---------------------------------------------------------------------------
# EffectRenderer — render pipeline
# ---------------------------------------------------------------------------


def test_renderer_maps_effect_value_through_palette_to_produce_packed_color() -> None:
    # Effect always returns 1.0; black→red palette maps 1.0 to full red.
    effect = Effect("test", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    color = renderer.render(state, 0.5)

    assert color == Palette.pack_rgb(255, 0, 0)


def test_renderer_returns_black_when_effect_value_is_zero() -> None:
    effect = Effect("test", lambda _: 0.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))  # black → red
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    color = renderer.render(state, 0.0)

    assert color == Palette.pack_rgb(0, 0, 0)


def test_renderer_update_propagates_to_effect_step() -> None:
    counter = CountUpdates()
    effect = Effect("test", lambda _: 0.0).add_steps([counter])
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = EffectRenderer(effect, palette)

    renderer.update(state, make_timer(0.016))
    renderer.update(state, make_timer(0.016))

    assert counter.count == 2


# ---------------------------------------------------------------------------
# AverageMergeRenderer
# ---------------------------------------------------------------------------


def test_average_merge_render_with_single_renderer_produces_same_color() -> None:
    effect = Effect("test", lambda _: 1.0)
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))  # black → red
    state = EffectState()
    single = EffectRenderer(effect, palette)
    merged = AverageMergeRenderer([EffectRenderer(effect, palette)])

    assert merged.render(state, 0.5) == single.render(state, 0.5)


def test_average_merge_render_averages_rgb_channels_across_renderers() -> None:
    # Renderer A → full red (255,0,0); Renderer B → full blue (0,0,255).
    # Average: r=(255+0)//2=127, g=0, b=(0+255)//2=127.
    red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    blue_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 0, 255]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = AverageMergeRenderer(
        [
            EffectRenderer(effect, red_palette),
            EffectRenderer(effect, blue_palette),
        ]
    )

    color = renderer.render(state, 0.0)

    assert color == Palette.pack_rgb(127, 0, 127)


def test_average_merge_update_propagates_to_all_child_renderers() -> None:
    counter_a = CountUpdates()
    counter_b = CountUpdates()
    effect_a = Effect("a", lambda _: 0.0).add_steps([counter_a])
    effect_b = Effect("b", lambda _: 0.0).add_steps([counter_b])
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = AverageMergeRenderer(
        [
            EffectRenderer(effect_a, palette),
            EffectRenderer(effect_b, palette),
        ]
    )

    renderer.update(state, make_timer(0.016))

    assert counter_a.count == 1
    assert counter_b.count == 1


# ---------------------------------------------------------------------------
# AdditiveMergeRenderer
# ---------------------------------------------------------------------------


def test_additive_merge_render_sums_rgb_channels_from_each_renderer() -> None:
    # Each renderer produces r=64; two renderers → r=128.
    dim_red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 64, 0, 0]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = AdditiveMergeRenderer(
        [
            EffectRenderer(effect, dim_red_palette),
            EffectRenderer(effect, dim_red_palette),
        ]
    )

    color = renderer.render(state, 0.0)

    assert color == Palette.pack_rgb(128, 0, 0)


def test_additive_merge_render_clamps_summed_channel_to_255_on_overflow() -> None:
    # Each renderer produces g=128; sum=256 → clamped to 255.
    green_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 128, 0]))
    effect = Effect("test", lambda _: 1.0)
    state = EffectState()
    renderer = AdditiveMergeRenderer(
        [
            EffectRenderer(effect, green_palette),
            EffectRenderer(effect, green_palette),
        ]
    )

    color = renderer.render(state, 0.0)

    assert color == Palette.pack_rgb(0, 255, 0)


def test_additive_merge_update_propagates_to_all_child_renderers() -> None:
    counter_a = CountUpdates()
    counter_b = CountUpdates()
    effect_a = Effect("a", lambda _: 0.0).add_steps([counter_a])
    effect_b = Effect("b", lambda _: 0.0).add_steps([counter_b])
    palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
    state = EffectState()
    renderer = AdditiveMergeRenderer(
        [
            EffectRenderer(effect_a, palette),
            EffectRenderer(effect_b, palette),
        ]
    )

    renderer.update(state, make_timer(0.016))

    assert counter_a.count == 1
    assert counter_b.count == 1
