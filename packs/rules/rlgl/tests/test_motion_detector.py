"""Tests for motion_magnitude() pure function."""

from __future__ import annotations

import pytest

from engine.input import AccelerationData
from packs.rules.rlgl.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    RED_MAX_MOTION_THRESHOLD,
    motion_magnitude,
)

_G = AccelerationData.GRAVITY


def test_device_at_rest_returns_near_zero():
    """A device lying flat has ~GRAVITY on one axis; dynamic component is ~0."""
    accel = AccelerationData(x=0.0, y=0.0, z=_G)
    result = motion_magnitude(accel)
    assert result == pytest.approx(0.0, abs=1e-9)


def test_device_at_rest_tilted_returns_near_zero():
    """GRAVITY split across two axes (tilted device) still sums to GRAVITY."""
    # 1/sqrt(2) ≈ 0.7071; sqrt(2) * (G/sqrt(2))² = G² so total magnitude = G
    g_axis = _G * 0.7071067811865476
    accel = AccelerationData(x=g_axis, y=g_axis, z=0.0)
    result = motion_magnitude(accel)
    assert result == pytest.approx(0.0, abs=1e-6)


def test_moderate_movement_exceeds_threshold():
    """A wrist-flick magnitude above RED_MAX_MOTION_THRESHOLD is returned."""
    # 2 m/s² dynamic acceleration along the gravity axis → clean 2.0 result
    accel = AccelerationData(x=0.0, y=0.0, z=_G + 2.0)
    result = motion_magnitude(accel)
    assert result == pytest.approx(2.0, abs=1e-9)
    assert result > RED_MAX_MOTION_THRESHOLD


def test_strong_multi_axis_movement_returns_magnitude_minus_gravity():
    """Very strong movement across all axes returns raw_magnitude - GRAVITY."""
    # sqrt(20²+20²+20²) = sqrt(1200) ≈ 34.64; subtract GRAVITY ≈ 24.83
    accel = AccelerationData(x=20.0, y=20.0, z=20.0)
    result = motion_magnitude(accel)
    assert result > RED_MAX_MOTION_THRESHOLD
    # 34.641... - 9.81 = 24.83... — just confirm it's in the right ballpark
    assert result == pytest.approx(24.83, abs=0.05)


def test_negative_axis_values_do_not_produce_negative_result():
    """Free-fall / sensor dropout scenario: magnitude below GRAVITY → clamped to 0.0."""
    accel = AccelerationData(x=0.0, y=0.0, z=0.0)
    result = motion_magnitude(accel)
    assert result == 0.0


def test_all_negative_axes_do_not_produce_negative_result():
    """Axes pointing opposite direction to normal — still clamped to 0.0."""
    accel = AccelerationData(x=-1.0, y=-1.0, z=-1.0)
    result = motion_magnitude(accel)
    assert result == 0.0


def test_result_is_always_non_negative():
    """Property: motion_magnitude never returns a negative float."""
    samples = [
        AccelerationData(0.0, 0.0, 0.0),
        AccelerationData(_G, 0.0, 0.0),
        AccelerationData(0.0, _G, 0.0),
        AccelerationData(0.0, 0.0, _G),
        AccelerationData(-_G, 0.0, 0.0),
        AccelerationData(-5.0, -5.0, -5.0),
    ]
    for accel in samples:
        assert motion_magnitude(accel) >= 0.0


def test_red_max_motion_threshold_is_defined():
    assert pytest.approx(1.5) == RED_MAX_MOTION_THRESHOLD


def test_green_min_motion_threshold_is_defined():
    assert pytest.approx(1.0) == GREEN_MIN_MOTION_THRESHOLD
