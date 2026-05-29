from effects.layers.renderer import LayerRenderer
from effects.palette import PaletteLUT256
from effects.render import PixelBuffer

_BLACK_TO_WHITE = bytes([0, 0, 0, 0, 255, 255, 255, 255])


class _ConstantLayer:
    """Layer that always returns a fixed value."""

    def __init__(self, value: float) -> None:
        self._value = value
        self.update_count = 0
        self.last_elapsed: float = 0.0

    def update(self, elapsed: float) -> None:
        self.update_count += 1
        self.last_elapsed = elapsed

    def sample(self, position: float, pixel_count: int) -> float:
        return self._value


# ---------------------------------------------------------------------------
# LayerRenderer — render output
# ---------------------------------------------------------------------------


def test_layer_renderer_maps_layer_sample_through_palette_for_each_pixel() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    layer = _ConstantLayer(0.5)
    renderer = LayerRenderer("test", layer, palette)

    output = PixelBuffer(5)
    renderer.render(output)

    expected = palette.lookup(0.5)
    for i in range(5):
        assert output[i] == expected


def test_layer_renderer_passes_normalized_position_per_pixel_to_layer() -> None:
    # gradient layer: sample(pos, count) = pos
    class _GradientLayer:
        def update(self, elapsed: float) -> None:
            pass

        def sample(self, position: float, pixel_count: int) -> float:
            return position

    palette = PaletteLUT256(_BLACK_TO_WHITE)
    renderer = LayerRenderer("test", _GradientLayer(), palette)

    count = 4
    output = PixelBuffer(count)
    renderer.render(output)

    for i in range(count):
        pos = i / count
        assert output[i] == palette.lookup(pos)


# ---------------------------------------------------------------------------
# LayerRenderer — update advances layer
# ---------------------------------------------------------------------------


def test_layer_renderer_update_passes_elapsed_to_layer() -> None:
    layer = _ConstantLayer(0.5)
    renderer = LayerRenderer("test", layer, PaletteLUT256(_BLACK_TO_WHITE))

    renderer.update(0.25)

    assert layer.update_count == 1
    assert abs(layer.last_elapsed - 0.25) < 1e-9


# ---------------------------------------------------------------------------
# LayerRenderer — name property
# ---------------------------------------------------------------------------


def test_layer_renderer_name_returns_name_passed_at_construction() -> None:
    renderer = LayerRenderer("elements.fire", _ConstantLayer(0.0), PaletteLUT256(_BLACK_TO_WHITE))

    assert renderer.name == "elements.fire"
