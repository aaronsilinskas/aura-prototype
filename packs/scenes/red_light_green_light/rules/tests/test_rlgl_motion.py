"""Tests for ``RlglMotion`` — gravity tracking, re-seeding, EMA smoothing,
and the ``rlgl_motion`` get-or-create accessor."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import AccelerationData
from engine.state import SceneControls, StateSlot
from engine.tests.helpers import SpyEffectControls
from packs.scenes.red_light_green_light.rules.helpers.rlgl_motion import (
    RlglMotion,
    rlgl_motion,
)

_G = AccelerationData.GRAVITY
_AT_REST = AccelerationData(x=0.0, y=0.0, z=_G)


class _StubTimer:
    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass


def _make_state(initial_data: dict | None = None):
    spy = SpyEffectControls()
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    return engine.create_state(SceneControls(), initial_data=initial_data or {})


# ---------------------------------------------------------------------------
# Gravity isolation — first sample seeds gravity, no motion is registered
# ---------------------------------------------------------------------------


def test_first_update_seeds_gravity_and_reports_no_motion():
    """The first sample after construction seeds gravity rather than starting
    at zero, so a device held steady reads zero motion immediately."""
    motion = RlglMotion()

    ema = motion.update(_AT_REST, gravity_beta=0.1, motion_smoothing=1.0)

    assert pytest.approx(0.0) == ema


def test_update_reports_motion_relative_to_seeded_gravity():
    """Once gravity is seeded, a deviation from it reads as motion."""
    motion = RlglMotion()
    motion.update(_AT_REST, gravity_beta=0.0, motion_smoothing=1.0)

    moved = AccelerationData(x=0.0, y=0.0, z=_G + 2.0)
    ema = motion.update(moved, gravity_beta=0.0, motion_smoothing=1.0)

    assert pytest.approx(2.0) == ema


# ---------------------------------------------------------------------------
# reset_gravity — re-seeds from the first sample of the next phase
# ---------------------------------------------------------------------------


def test_reset_gravity_reseeds_from_the_next_sample_instead_of_carrying_over():
    """After reset_gravity, the next update seeds gravity fresh from that
    sample rather than carrying over the old orientation."""
    motion = RlglMotion()
    motion.update(_AT_REST, gravity_beta=0.0, motion_smoothing=1.0)

    motion.reset_gravity()

    new_orientation = AccelerationData(x=_G, y=0.0, z=0.0)
    ema = motion.update(new_orientation, gravity_beta=0.0, motion_smoothing=1.0)

    # The new orientation is immediately treated as "at rest" — zero motion —
    # because gravity was re-seeded from it, not carried over from the old axis.
    assert pytest.approx(0.0) == ema


# ---------------------------------------------------------------------------
# EMA smoothing
# ---------------------------------------------------------------------------


def test_update_smooths_motion_with_the_given_factor():
    """A lone spike is smoothed toward but not equal to the raw deviation."""
    motion = RlglMotion()
    motion.update(_AT_REST, gravity_beta=0.0, motion_smoothing=0.5)

    spike = AccelerationData(x=0.0, y=0.0, z=_G + 2.0)
    ema = motion.update(spike, gravity_beta=0.0, motion_smoothing=0.5)

    # low_pass(0.0, 2.0, 0.5) == 1.0
    assert pytest.approx(1.0) == ema


# ---------------------------------------------------------------------------
# rlgl_motion — get-or-create accessor
# ---------------------------------------------------------------------------


def test_rlgl_motion_caches_the_same_instance_across_calls():
    """Gravity and EMA tracking must persist across ticks, so the accessor
    must return the same instance rather than rebuilding it each time."""
    state = _make_state()

    first = rlgl_motion(state)
    second = rlgl_motion(state)

    assert first is second


def test_rlgl_motion_is_a_state_slot():
    """rlgl_motion must be a StateSlot so that the key, factory, and
    revalidate cast are owned in one place with no # type: ignore at
    call sites."""
    assert isinstance(rlgl_motion, StateSlot)
