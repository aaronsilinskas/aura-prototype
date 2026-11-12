import tracemalloc

from effects.effect import PixelBuffer
from effects.layers.progress_layer import ProgressLayer
from effects.layers.progress_renderer import ProgressRenderer


def _render(progress: float, color: int, pixel_count: int = 10) -> list[int]:
    output = PixelBuffer(pixel_count)
    ProgressRenderer(ProgressLayer(progress), color).render(output)
    return list(output)


def test_progress_renderer_empty_progress_renders_all_dark() -> None:
    assert _render(0.0, 0xFFFFFF) == [0x000000] * 10


def test_progress_renderer_full_progress_renders_every_pixel_at_color() -> None:
    assert _render(1.0, 0x12AB34) == [0x12AB34] * 10


def test_progress_renderer_partial_progress_lights_first_pixels_and_leaves_rest_dark() -> None:
    # 10 pixels at 0.5 → exactly 5 lit, no boundary pixel.
    assert _render(0.5, 0xFFFFFF) == [0xFFFFFF] * 5 + [0x000000] * 5


def test_progress_renderer_dims_boundary_pixel_by_its_lit_fraction() -> None:
    # 10 pixels at 0.55 → pixel 5 is half lit: int(255 * 0.5) = 0x7F per channel.
    pixels = _render(0.55, 0xFFFFFF)

    assert pixels[5] == 0x7F7F7F


def test_progress_renderer_scales_each_color_channel_independently() -> None:
    # Half-lit boundary pixel of 0xFF8040 → 0x7F, 0x40, 0x20.
    assert _render(0.55, 0xFF8040)[5] == 0x7F4020


def test_progress_renderer_update_leaves_progress_unchanged() -> None:
    renderer = ProgressRenderer(ProgressLayer(0.55), 0xFFFFFF)
    before = PixelBuffer(10)
    renderer.render(before)

    renderer.update(1.0)
    after = PixelBuffer(10)
    renderer.render(after)

    assert list(after) == list(before)


def test_progress_renderer_steady_state_render_allocates_nothing_per_frame() -> None:
    # A per-frame list of 1000 entries would cost over 8 KB; the transient
    # ints of the colour arithmetic stay far below 1 KB.
    renderer = ProgressRenderer(ProgressLayer(0.5005), 0xFF8040)
    output = PixelBuffer(1000)
    renderer.render(output)

    tracemalloc.start()
    try:
        baseline, _ = tracemalloc.get_traced_memory()
        renderer.render(output)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak - baseline < 1024
