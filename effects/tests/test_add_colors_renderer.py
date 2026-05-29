from effects.add_colors_renderer import AddColorsRenderer
from effects.palette import Palette, PaletteLUT256
from effects.render import PixelBuffer
from effects.tests.helpers import make_timer

_BLACK_TO_WHITE = bytes([0, 0, 0, 0, 255, 255, 255, 255])


class _ConstantLayer:
    def __init__(self, value: float) -> None:
        self._value = value
        self.update_count = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def sample(self, position: float, pixel_count: int) -> float:
        return self._value


# ---------------------------------------------------------------------------
# AddColorsRenderer — single layer (no blending path)
# ---------------------------------------------------------------------------


def test_add_colors_renderer_with_one_layer_matches_layer_renderer_output() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    layer = _ConstantLayer(0.5)
    renderer = AddColorsRenderer("test", [(layer, palette)])

    output = PixelBuffer(4)
    renderer.render(None, output)

    expected = palette.lookup(0.5)
    for i in range(4):
        assert output[i] == expected


# ---------------------------------------------------------------------------
# AddColorsRenderer — additive blending
# ---------------------------------------------------------------------------


def test_add_colors_renderer_two_layers_are_brighter_than_one() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    renderer_two = AddColorsRenderer(
        "two", [(_ConstantLayer(0.5), palette), (_ConstantLayer(0.5), palette)]
    )
    renderer_one = AddColorsRenderer("one", [(_ConstantLayer(0.5), palette)])

    out_two = PixelBuffer(4)
    out_one = PixelBuffer(4)
    renderer_two.render(None, out_two)
    renderer_one.render(None, out_one)

    # Additive blend: each channel is brighter (or equal at max 255)
    assert out_two[0] > out_one[0], "additive result not brighter than single layer"


def test_add_colors_renderer_blends_channels_additively_without_overflow() -> None:
    # Palette: maps 1.0 → packed (100, 50, 25)
    # Two layers both at 1.0 → result should be (200, 100, 50)
    dim_red_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 100, 50, 25]))
    renderer = AddColorsRenderer(
        "test",
        [(_ConstantLayer(1.0), dim_red_palette), (_ConstantLayer(1.0), dim_red_palette)],
    )

    output = PixelBuffer(1)
    renderer.render(None, output)

    r = (output[0] >> 16) & 255
    g = (output[0] >> 8) & 255
    b = output[0] & 255
    assert r == 200
    assert g == 100
    assert b == 50


def test_add_colors_renderer_clamps_channels_at_255() -> None:
    # Palette maps 1.0 → (200, 200, 200); two layers → would be (400,400,400),
    # clamped to (255,255,255)
    bright_palette = PaletteLUT256(bytes([0, 0, 0, 0, 255, 200, 200, 200]))
    renderer = AddColorsRenderer(
        "test",
        [(_ConstantLayer(1.0), bright_palette), (_ConstantLayer(1.0), bright_palette)],
    )

    output = PixelBuffer(1)
    renderer.render(None, output)

    assert output[0] == Palette.pack_rgb(255, 255, 255)


# ---------------------------------------------------------------------------
# AddColorsRenderer — update advances all layers
# ---------------------------------------------------------------------------


def test_add_colors_renderer_update_advances_all_layers() -> None:
    layer_a = _ConstantLayer(0.5)
    layer_b = _ConstantLayer(0.3)
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    renderer = AddColorsRenderer("test", [(layer_a, palette), (layer_b, palette)])

    renderer.update(None, make_timer(0.1))

    assert layer_a.update_count == 1
    assert layer_b.update_count == 1
