from effects.layers.add_samples_renderer import AddSamplesRenderer
from effects.palette import PaletteLUT256
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
# AddSamplesRenderer — render output
# ---------------------------------------------------------------------------


def test_add_samples_renderer_single_layer_maps_sample_through_palette() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    renderer = AddSamplesRenderer("test", [_ConstantLayer(0.5)], palette)

    output = PixelBuffer(4)
    renderer.render(output)

    expected = palette.lookup(0.5)
    for i in range(4):
        assert output[i] == expected


def test_add_samples_renderer_sums_layer_samples_before_palette_lookup() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    # two layers at 0.3 each → sum = 0.6
    renderer = AddSamplesRenderer("test", [_ConstantLayer(0.3), _ConstantLayer(0.3)], palette)

    output = PixelBuffer(1)
    renderer.render(output)

    assert output[0] == palette.lookup(0.6)


def test_add_samples_renderer_clamps_sum_to_one_before_palette_lookup() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    # two layers at 0.8 each → sum = 1.6, clamped to 1.0
    renderer = AddSamplesRenderer("test", [_ConstantLayer(0.8), _ConstantLayer(0.8)], palette)

    output = PixelBuffer(1)
    renderer.render(output)

    # Should equal palette.lookup(1.0), not palette.lookup(1.6)
    assert output[0] == palette.lookup(1.0)


def test_add_samples_renderer_two_layers_produce_brighter_output_than_one() -> None:
    palette = PaletteLUT256(_BLACK_TO_WHITE)
    renderer_two = AddSamplesRenderer("two", [_ConstantLayer(0.3), _ConstantLayer(0.3)], palette)
    renderer_one = AddSamplesRenderer("one", [_ConstantLayer(0.3)], palette)

    out_two = PixelBuffer(4)
    out_one = PixelBuffer(4)
    renderer_two.render(out_two)
    renderer_one.render(out_one)

    assert out_two[0] > out_one[0]


# ---------------------------------------------------------------------------
# AddSamplesRenderer — update advances all layers
# ---------------------------------------------------------------------------


def test_add_samples_renderer_update_advances_all_layers() -> None:
    layer_a = _ConstantLayer(0.3)
    layer_b = _ConstantLayer(0.3)
    renderer = AddSamplesRenderer("test", [layer_a, layer_b], PaletteLUT256(_BLACK_TO_WHITE))

    renderer.update(make_timer(0.1))

    assert layer_a.update_count == 1
    assert layer_b.update_count == 1


# ---------------------------------------------------------------------------
# AddSamplesRenderer — name property
# ---------------------------------------------------------------------------


def test_add_samples_renderer_name_returns_name_passed_at_construction() -> None:
    renderer = AddSamplesRenderer(
        "elements.air", [_ConstantLayer(0.0)], PaletteLUT256(_BLACK_TO_WHITE)
    )

    assert renderer.name == "elements.air"
