import pytest

from effects.shape import Shape
from effects.value import GAMMA_FACTOR

# ---------------------------------------------------------------------------
# Shape.none
# ---------------------------------------------------------------------------


def test_none_shape_produces_zero_everywhere() -> None:
    shape = Shape.none()

    assert shape(0.0) == 0.0
    assert shape(0.5) == 0.0
    assert shape(1.0) == 0.0


# ---------------------------------------------------------------------------
# Shape.gradient
# ---------------------------------------------------------------------------


def test_gradient_is_zero_at_start_of_strip() -> None:
    shape = Shape.gradient()

    assert shape(0.0) == pytest.approx(0.0)


def test_gradient_approaches_one_near_end_of_strip() -> None:
    # Position 1.0 wraps to 0.0 via modulo, so use a value just below 1.0.
    shape = Shape.gradient()

    assert shape(0.9999) == pytest.approx(pow(0.9999, GAMMA_FACTOR), rel=1e-4)


def test_gradient_is_monotonically_increasing_across_strip() -> None:
    # Exclude position 1.0 — it wraps to 0.0 via modulo, which is the same as
    # the strip start, not a point beyond the end.
    shape = Shape.gradient()
    positions = [i / 20 for i in range(20)]

    values = [shape(p) for p in positions]

    for i in range(len(values) - 1):
        assert values[i] <= values[i + 1]


def test_gradient_applies_gamma_correction_not_a_linear_ramp() -> None:
    shape = Shape.gradient()

    assert shape(0.5) == pytest.approx(pow(0.5, GAMMA_FACTOR))


def test_gradient_wraps_out_of_range_positions() -> None:
    shape = Shape.gradient()

    assert shape(1.5) == pytest.approx(shape(0.5))


# ---------------------------------------------------------------------------
# Shape.centered_gradient
# ---------------------------------------------------------------------------


def test_centered_gradient_peaks_at_center_of_strip() -> None:
    shape = Shape.centered_gradient()

    assert shape(0.5) == pytest.approx(1.0)


def test_centered_gradient_is_zero_at_left_edge() -> None:
    shape = Shape.centered_gradient()

    assert shape(0.0) == pytest.approx(0.0)


def test_centered_gradient_is_symmetric_near_right_edge() -> None:
    # Position 1.0 wraps to 0.0 via modulo; just inside the upper edge should
    # mirror the corresponding point near the lower edge.
    shape = Shape.centered_gradient()

    assert shape(0.9999) == pytest.approx(shape(0.0001), rel=1e-3)


def test_centered_gradient_is_symmetric_around_center() -> None:
    shape = Shape.centered_gradient()

    for i in range(1, 10):
        t = i / 20.0  # sample in first half
        mirror = 1.0 - t  # mirror in second half
        assert shape(t) == pytest.approx(shape(mirror), rel=1e-6)


def test_centered_gradient_wraps_out_of_range_positions() -> None:
    shape = Shape.centered_gradient()

    assert shape(1.25) == pytest.approx(shape(0.25))


# ---------------------------------------------------------------------------
# Shape.padded
# ---------------------------------------------------------------------------


def test_padded_returns_zero_inside_leading_padding_zone() -> None:
    shape = Shape.padded(0.2, lambda _: 1.0)

    assert shape(0.1) == pytest.approx(0.0)


def test_padded_returns_zero_inside_trailing_padding_zone() -> None:
    shape = Shape.padded(0.2, lambda _: 1.0)

    assert shape(0.9) == pytest.approx(0.0)


def test_padded_delegates_to_inner_shape_inside_active_span() -> None:
    # Inner shape is a flat 0.6; any position in the active region should return 0.6.
    shape = Shape.padded(0.25, lambda _: 0.6)

    assert shape(0.5) == pytest.approx(0.6)


def test_padded_remaps_inner_span_to_full_zero_to_one_range() -> None:
    # With 0.25 padding on each side, the active span is [0.25, 0.75].
    # The inner shape receives a position remapped into [0.0, 1.0].
    received: list[float] = []

    def probe(pos: float) -> float:
        received.append(pos)
        return 0.0

    shape = Shape.padded(0.25, probe)
    shape(0.25)  # at the start of the active span → inner position 0.0
    shape(0.75)  # at the end → inner position 1.0

    assert received[0] == pytest.approx(0.0, abs=1e-6)
    assert received[1] == pytest.approx(1.0, abs=1e-6)


def test_padded_with_full_padding_returns_zero_everywhere() -> None:
    shape = Shape.padded(0.5, lambda _: 1.0)

    assert shape(0.0) == 0.0
    assert shape(0.5) == 0.0
    assert shape(0.99) == 0.0


def test_padded_wraps_out_of_range_positions() -> None:
    # Position 1.1 wraps to 0.1, which falls inside the padding zone.
    shape = Shape.padded(0.2, lambda _: 1.0)

    assert shape(1.1) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Shape.reverse
# ---------------------------------------------------------------------------


def test_reverse_maps_start_of_strip_to_end_of_inner_shape() -> None:
    # gradient(1.0) wraps to 0.0, so use a shape that returns the raw position.
    shape = Shape.reverse(lambda pos: pos)

    assert shape(0.0) == pytest.approx(1.0)


def test_reverse_maps_end_of_strip_to_start_of_inner_shape() -> None:
    # Position 1.0 wraps to 0.0 via modulo (same as the strip start), so use
    # a value just below 1.0 to represent the far end of the strip.
    shape = Shape.reverse(lambda pos: pos)

    assert shape(0.9999) == pytest.approx(0.0001, abs=1e-4)


# ---------------------------------------------------------------------------
# Shape.sine
# ---------------------------------------------------------------------------


def test_sine_midpoint_is_halfway_between_min_and_max() -> None:
    shape = Shape.sine(1)

    # At position 0.0, sin(0) = 0, so output is 0.5.
    assert shape(0.0) == pytest.approx(0.5)


def test_sine_output_stays_within_zero_to_one() -> None:
    shape = Shape.sine(3)
    positions = [i / 100 for i in range(101)]

    for pos in positions:
        value = shape(pos)
        assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Shape.checkers
# ---------------------------------------------------------------------------


def test_checkers_returns_flat_value_at_start_of_each_segment() -> None:
    shape = Shape.checkers(0.8, count=4, width=0.3)

    # With 4 checkers, each segment is 0.25 wide. Position 0.0 is at the start.
    assert shape(0.0) == pytest.approx(0.8)


def test_checkers_returns_zero_past_the_fade_region() -> None:
    shape = Shape.checkers(1.0, count=2, width=0.2)

    # Segment span is 0.5. Flat region is [0, 0.2), fade is [0.2, 0.4), dark is [0.4, 0.5).
    assert shape(0.45) == pytest.approx(0.0)


def test_checkers_with_zero_count_produces_no_output() -> None:
    shape = Shape.checkers(1.0, count=0, width=0.5)

    assert shape(0.0) == 0.0
    assert shape(0.5) == 0.0
