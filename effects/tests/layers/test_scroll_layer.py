import pytest

from effects.layers.scroll import ScrollOffset
from effects.layers.scroll_layer import ScrollLayer


class _PositionLayer:
    """Layer whose sample returns the position passed to it."""

    def update(self, elapsed: float) -> None:
        pass

    def sample(self, position: float, pixel_count: int) -> float:
        return position


class _UpdateCountLayer:
    """Layer that records how many times update was called."""

    def __init__(self) -> None:
        self.update_count = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def sample(self, position: float, pixel_count: int) -> float:
        return 0.0


# ---------------------------------------------------------------------------
# ScrollLayer — position transformation
# ---------------------------------------------------------------------------


def test_scroll_layer_does_not_shift_position_before_update() -> None:
    layer = ScrollLayer(_PositionLayer(), ScrollOffset(speed=1.0))

    # offset is zero, so apply(0.5) = 0.5 → inner returns 0.5
    assert layer.sample(0.5, 10) == 0.5


def test_scroll_layer_shifts_sample_position_after_update() -> None:
    layer = ScrollLayer(_PositionLayer(), ScrollOffset(speed=1.0))

    layer.update(0.25)  # offset becomes 0.25

    # inner receives apply(0.0) = 0.25
    assert layer.sample(0.0, 10) == pytest.approx(0.25)


def test_scroll_layer_delegates_update_to_inner_layer() -> None:
    inner = _UpdateCountLayer()
    layer = ScrollLayer(inner, ScrollOffset(speed=0.0))

    layer.update(0.016)
    layer.update(0.016)

    assert inner.update_count == 2


def test_scroll_layer_passes_pixel_count_to_inner_sample() -> None:
    recorded: list[int] = []

    class _RecordPixelCount:
        def update(self, elapsed: float) -> None:
            pass

        def sample(self, position: float, pixel_count: int) -> float:
            recorded.append(pixel_count)
            return 0.0

    layer = ScrollLayer(_RecordPixelCount(), ScrollOffset(speed=0.0))
    layer.sample(0.5, 42)

    assert recorded == [42]
