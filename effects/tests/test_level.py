import pytest

from effects.level import clamp_level, level_lerp, level_lerp_int, level_progress

# ---------------------------------------------------------------------------
# clamp_level
# ---------------------------------------------------------------------------


def test_clamp_level_returns_level_unchanged_within_valid_range() -> None:
    for level in range(1, 11):
        assert clamp_level(level) == level


def test_clamp_level_clamps_below_minimum_to_one() -> None:
    assert clamp_level(0) == 1
    assert clamp_level(-100) == 1


def test_clamp_level_clamps_above_maximum_to_ten() -> None:
    assert clamp_level(11) == 10
    assert clamp_level(100) == 10


# ---------------------------------------------------------------------------
# level_progress
# ---------------------------------------------------------------------------


def test_level_progress_maps_each_level_to_correct_normalized_value() -> None:
    for level in range(1, 11):
        assert level_progress(level) == pytest.approx((level - 1) / 9)


def test_level_progress_clamps_out_of_range_input() -> None:
    assert level_progress(0) == pytest.approx(0.0)
    assert level_progress(11) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# level_lerp
# ---------------------------------------------------------------------------


def test_level_lerp_maps_each_level_to_correct_interpolated_value() -> None:
    for level in range(1, 11):
        progress = (level - 1) / 9
        assert level_lerp(level, 0.2, 0.8) == pytest.approx(0.2 + progress * 0.6)


def test_level_lerp_clamps_out_of_range_level() -> None:
    assert level_lerp(0, 0.0, 1.0) == pytest.approx(0.0)
    assert level_lerp(11, 0.0, 1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# level_lerp_int
# ---------------------------------------------------------------------------


def test_level_lerp_int_maps_each_level_to_correct_rounded_value() -> None:
    for level in range(1, 11):
        progress = (level - 1) / 9
        expected = int(10 + progress * 190 + 0.5)
        assert level_lerp_int(level, 10, 200) == expected
