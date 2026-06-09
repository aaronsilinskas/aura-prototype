"""Tests for engine.lerp — general-purpose lerp utilities."""

from __future__ import annotations

import pytest

from engine.lerp import level_lerp


def test_level_lerp_at_level_1_returns_max_val():
    """Level 1 is easiest — result should be max_val."""
    assert level_lerp(1, max_val=5.0, min_val=2.0, max_level=10) == pytest.approx(5.0)


def test_level_lerp_at_max_level_returns_min_val():
    """Level max_level is hardest — result should be min_val."""
    assert level_lerp(10, max_val=5.0, min_val=2.0, max_level=10) == pytest.approx(2.0)


def test_level_lerp_at_midpoint_returns_interpolated_value():
    """Level 5 (out of 9 steps from 1 to 10) should be fraction=4/9 of the way."""
    fraction = (5 - 1) / (10 - 1)
    expected = 5.0 + (2.0 - 5.0) * fraction
    assert level_lerp(5, max_val=5.0, min_val=2.0, max_level=10) == pytest.approx(expected)


def test_level_lerp_max_level_1_guard_returns_max_val():
    """When max_level == 1, fraction is guarded to 0 — always returns max_val."""
    assert level_lerp(1, max_val=5.0, min_val=2.0, max_level=1) == pytest.approx(5.0)


def test_level_lerp_max_level_0_guard_returns_max_val():
    """When max_level == 0 (≤ 1), fraction is guarded to 0 — always returns max_val."""
    assert level_lerp(1, max_val=5.0, min_val=2.0, max_level=0) == pytest.approx(5.0)


def test_level_lerp_level_below_1_is_clamped_to_max_val():
    """Level below 1 is clamped to fraction=0.0 — returns max_val."""
    assert level_lerp(0, max_val=5.0, min_val=2.0, max_level=10) == pytest.approx(5.0)


def test_level_lerp_level_above_max_level_is_clamped_to_min_val():
    """Level above max_level is clamped to fraction=1.0 — returns min_val."""
    assert level_lerp(99, max_val=5.0, min_val=2.0, max_level=10) == pytest.approx(2.0)
