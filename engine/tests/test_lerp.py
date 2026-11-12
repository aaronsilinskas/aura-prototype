"""Tests for engine.lerp — the one level interpolation, shared by Game and Effect Levels."""

from __future__ import annotations

import pytest

from engine.lerp import level_lerp, level_lerp_int

# ---------------------------------------------------------------------------
# level_lerp — falling pair (value shrinks as the level rises)
# ---------------------------------------------------------------------------


def test_level_lerp_falling_pair_at_level_1_returns_first_value():
    assert level_lerp(1, first_value=5.0, top_value=2.0, top_level=10) == pytest.approx(5.0)


def test_level_lerp_falling_pair_at_top_level_returns_top_value():
    assert level_lerp(10, first_value=5.0, top_value=2.0, top_level=10) == pytest.approx(2.0)


def test_level_lerp_falling_pair_at_midpoint_blends_by_level_fraction():
    """Level 4 of 1..7 is halfway: 5.0 → 2.0 gives 3.5."""
    assert level_lerp(4, first_value=5.0, top_value=2.0, top_level=7) == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# level_lerp — rising pair (value grows as the level rises)
# ---------------------------------------------------------------------------


def test_level_lerp_rising_pair_at_level_1_returns_first_value():
    assert level_lerp(1, first_value=0.2, top_value=0.8, top_level=10) == pytest.approx(0.2)


def test_level_lerp_rising_pair_at_top_level_returns_top_value():
    assert level_lerp(10, first_value=0.2, top_value=0.8, top_level=10) == pytest.approx(0.8)


def test_level_lerp_rising_pair_at_midpoint_blends_by_level_fraction():
    """Level 4 of 1..10 is a third of the way: 0.2 → 0.8 gives 0.4."""
    assert level_lerp(4, first_value=0.2, top_value=0.8, top_level=10) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# level_lerp — out-of-range levels and degenerate top levels
# ---------------------------------------------------------------------------


def test_level_lerp_level_below_1_returns_first_value():
    assert level_lerp(0, first_value=5.0, top_value=2.0, top_level=10) == pytest.approx(5.0)
    assert level_lerp(-3, first_value=0.2, top_value=0.8, top_level=10) == pytest.approx(0.2)


def test_level_lerp_level_above_top_level_returns_top_value():
    assert level_lerp(99, first_value=5.0, top_value=2.0, top_level=10) == pytest.approx(2.0)
    assert level_lerp(11, first_value=0.2, top_value=0.8, top_level=10) == pytest.approx(0.8)


def test_level_lerp_top_level_1_returns_first_value_at_any_level():
    assert level_lerp(1, first_value=5.0, top_value=2.0, top_level=1) == pytest.approx(5.0)
    assert level_lerp(3, first_value=5.0, top_value=2.0, top_level=1) == pytest.approx(5.0)


def test_level_lerp_top_level_below_1_returns_first_value():
    assert level_lerp(1, first_value=5.0, top_value=2.0, top_level=0) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# level_lerp_int
# ---------------------------------------------------------------------------


def test_level_lerp_int_rounds_to_nearest_whole_number_at_each_level():
    """10 → 20 over levels 1..5 steps by 2.5: 10, 12.5, 15, 17.5, 20 (halves round up)."""
    results = [level_lerp_int(level, 10, 20, 5) for level in range(1, 6)]
    assert results == [10, 13, 15, 18, 20]


def test_level_lerp_int_rounds_a_falling_pair_to_nearest_whole_number():
    """7 → 0 over levels 1..4 is 7, 4.67, 2.33, 0."""
    results = [level_lerp_int(level, 7, 0, 4) for level in range(1, 5)]
    assert results == [7, 5, 2, 0]


def test_level_lerp_int_clamps_out_of_range_levels_to_end_values():
    assert level_lerp_int(0, 10, 200, 10) == 10
    assert level_lerp_int(11, 10, 200, 10) == 200
