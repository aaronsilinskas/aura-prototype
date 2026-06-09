"""Tests for the motion-detection helpers: ``linear_magnitude``, ``low_pass``,
and the tuned threshold / filter constants."""

from __future__ import annotations

import pytest

from engine.input import AccelerationData
from packs.rules.rlgl.helpers.motion_detector import (
    GRAVITY_LOWPASS_BETA,
    GREEN_MIN_MOTION_THRESHOLD,
    MOTION_EMA_ALPHA,
    RED_MAX_MOTION_THRESHOLD,
    linear_magnitude,
    low_pass,
)

_G = AccelerationData.GRAVITY


# ---------------------------------------------------------------------------
# linear_magnitude() — gravity removed as a vector
# ---------------------------------------------------------------------------


def test_linear_magnitude_is_zero_when_acceleration_matches_gravity():
    """A device at rest (reading only the gravity vector) shows no motion."""
    accel = AccelerationData(x=0.0, y=0.0, z=_G)
    assert pytest.approx(0.0) == linear_magnitude(accel, 0.0, 0.0, _G)


def test_linear_magnitude_returns_distance_from_the_gravity_vector():
    """Motion is the magnitude of the sample minus the gravity estimate."""
    accel = AccelerationData(x=3.0, y=4.0, z=_G)  # deviation (3, 4, 0) → 5.0
    assert pytest.approx(5.0) == linear_magnitude(accel, 0.0, 0.0, _G)


def test_linear_magnitude_is_orientation_independent():
    """The same physical motion reads the same whether aligned with or
    perpendicular to gravity — the whole point of subtracting gravity as a vector."""
    along_gravity = AccelerationData(x=0.0, y=0.0, z=_G + 1.0)  # 1 m/s² parallel
    across_gravity = AccelerationData(x=1.0, y=0.0, z=_G)  # 1 m/s² perpendicular

    parallel = linear_magnitude(along_gravity, 0.0, 0.0, _G)
    perpendicular = linear_magnitude(across_gravity, 0.0, 0.0, _G)

    assert pytest.approx(1.0) == parallel
    assert pytest.approx(1.0) == perpendicular


# ---------------------------------------------------------------------------
# low_pass() — one-pole filter shared by gravity tracking and motion smoothing
# ---------------------------------------------------------------------------


def test_low_pass_eases_toward_the_sample_by_the_factor():
    """One step moves the running value a `factor` fraction toward the sample."""
    assert pytest.approx(1.0) == low_pass(0.0, 10.0, 0.1)


def test_low_pass_factor_of_one_snaps_to_the_sample():
    """factor == 1.0 disables smoothing — the value becomes the latest sample."""
    assert pytest.approx(5.0) == low_pass(99.0, 5.0, 1.0)


def test_low_pass_converges_to_a_held_sample():
    """A steady input is tracked: the value climbs toward and settles at it."""
    value = 0.0
    for _ in range(100):
        value = low_pass(value, _G, 0.1)
    assert pytest.approx(_G, abs=0.01) == value


def test_low_pass_decays_toward_zero_when_the_sample_stops():
    """Once the input drops to zero the value bleeds back down to zero."""
    value = _G
    for _ in range(100):
        value = low_pass(value, 0.0, 0.1)
    assert pytest.approx(0.0, abs=0.01) == value


# ---------------------------------------------------------------------------
# Tuned constants
# ---------------------------------------------------------------------------


def test_red_threshold_is_stricter_than_green_move_threshold():
    """Red must catch the smallest twitch; green requires deliberate movement."""
    assert RED_MAX_MOTION_THRESHOLD < GREEN_MIN_MOTION_THRESHOLD


def test_green_min_threshold_is_tuned_to_two():
    """Lock the hand-tuned Green threshold so a change to it is deliberate."""
    assert pytest.approx(2.0) == GREEN_MIN_MOTION_THRESHOLD


def test_gravity_tracking_is_slower_than_motion_smoothing():
    """Gravity must track slower than the motion signal, or real motion is
    absorbed into the gravity estimate before it ever registers."""
    assert GRAVITY_LOWPASS_BETA < MOTION_EMA_ALPHA
