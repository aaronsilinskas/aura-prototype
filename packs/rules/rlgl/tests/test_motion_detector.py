"""Tests for the motion-detection helpers: ``motion_magnitude``, ``smooth_motion``,
and the tuned threshold / smoothing constants."""

from __future__ import annotations

import pytest

from engine.input import AccelerationData
from packs.rules.rlgl.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    MOTION_EMA_ALPHA,
    RED_MAX_MOTION_THRESHOLD,
    motion_magnitude,
    smooth_motion,
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


def test_red_threshold_is_stricter_than_green_move_threshold():
    """Red must catch the smallest twitch; green requires deliberate movement."""
    assert RED_MAX_MOTION_THRESHOLD < GREEN_MIN_MOTION_THRESHOLD


def test_red_max_threshold_is_tuned_to_quarter():
    """Lock the hand-tuned Red threshold so a change to it is deliberate."""
    assert pytest.approx(0.25) == RED_MAX_MOTION_THRESHOLD


def test_green_min_threshold_is_tuned_to_one():
    """Lock the hand-tuned Green threshold so a change to it is deliberate."""
    assert pytest.approx(1.0) == GREEN_MIN_MOTION_THRESHOLD


# ---------------------------------------------------------------------------
# smooth_motion() — exponential moving average of motion magnitude
# ---------------------------------------------------------------------------

# A sample whose magnitude is well clear of any plausible threshold.
_STRONG = AccelerationData(x=0.0, y=0.0, z=_G + 4.0)  # motion_magnitude == 4.0
_STILL = AccelerationData(x=0.0, y=0.0, z=_G)  # motion_magnitude == 0.0


def test_first_sample_is_attenuated_by_alpha():
    """Folding one sample into a zero average yields alpha * magnitude."""
    ema = smooth_motion(0.0, _STRONG, alpha=0.3)
    assert ema == pytest.approx(0.3 * 4.0)


def test_a_lone_threshold_level_spike_smooths_below_the_move_threshold():
    """One sample at the move-threshold magnitude, smoothed, falls below the
    threshold — so a single noisy reading at gate level never reads as moving."""
    at_threshold = AccelerationData(x=0.0, y=0.0, z=_G + GREEN_MIN_MOTION_THRESHOLD)
    ema = smooth_motion(0.0, at_threshold, alpha=0.4)
    assert ema < GREEN_MIN_MOTION_THRESHOLD


def test_sustained_motion_converges_toward_the_true_magnitude():
    """Repeated identical samples drive the average toward the raw magnitude."""
    ema = 0.0
    for _ in range(20):
        ema = smooth_motion(ema, _STRONG, alpha=0.3)
    assert ema == pytest.approx(4.0, abs=0.05)


def test_sustained_stillness_decays_the_average_toward_zero():
    """Once motion stops, the average bleeds back down to zero."""
    ema = 4.0
    for _ in range(40):
        ema = smooth_motion(ema, _STILL, alpha=0.3)
    assert ema == pytest.approx(0.0, abs=0.05)


def test_alpha_of_one_disables_smoothing():
    """alpha == 1.0 makes the average equal the instantaneous magnitude."""
    ema = smooth_motion(99.0, _STRONG, alpha=1.0)
    assert ema == pytest.approx(motion_magnitude(_STRONG))


def test_default_alpha_is_used_when_unspecified():
    """Omitting ``alpha`` smooths with ``MOTION_EMA_ALPHA`` rather than some other rate."""
    assert smooth_motion(0.0, _STRONG) == smooth_motion(0.0, _STRONG, alpha=MOTION_EMA_ALPHA)
