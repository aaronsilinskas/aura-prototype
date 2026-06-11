"""Tests for ``RlglPhaseState`` -- phase/level/receipt state and the
``rlgl_phase_state`` get-or-create accessor."""

from __future__ import annotations

from engine.engine import GameEngine
from engine.state import EffectReceipt, SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import (
    PHASE_READY,
    RlglPhaseState,
    rlgl_phase_state,
)


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
# Construction defaults
# ---------------------------------------------------------------------------


def test_new_phase_state_starts_in_ready_with_level_one_and_no_receipts():
    """A freshly constructed phase state begins in Ready at level 1 with no
    in-flight receipts -- the bootstrap state the rule's first tick expects."""
    phase_state = RlglPhaseState()

    assert phase_state.phase == PHASE_READY
    assert phase_state.phase_start == 0.0
    assert phase_state.level == 1
    assert phase_state.music_receipt is None
    assert phase_state.level_receipt is None
    assert phase_state.win_sting_receipt is None


# ---------------------------------------------------------------------------
# enter -- sets phase + start, stops/clears music
# ---------------------------------------------------------------------------


def test_enter_sets_phase_and_phase_start():
    """enter() records the new phase and the time it was entered."""
    phase_state = RlglPhaseState()

    phase_state.enter("red", now=12.5)

    assert phase_state.phase == "red"
    assert phase_state.phase_start == 12.5


def test_enter_stops_and_clears_a_running_music_receipt():
    """A looping music effect from the previous phase must not leak into the
    next one -- enter() stops and clears it."""
    phase_state = RlglPhaseState()
    receipt = EffectReceipt(1)
    phase_state.music_receipt = receipt

    phase_state.enter("green_warning", now=5.0)

    assert receipt.is_stopped()
    assert phase_state.music_receipt is None


def test_enter_is_a_no_op_for_music_when_none_is_playing():
    """Entering a phase with no music playing does not raise."""
    phase_state = RlglPhaseState()

    phase_state.enter("red_warning", now=1.0)

    assert phase_state.music_receipt is None


# ---------------------------------------------------------------------------
# elapsed -- time since phase_start
# ---------------------------------------------------------------------------


def test_elapsed_returns_time_since_phase_start():
    """elapsed() reports how long the current phase has been running."""
    phase_state = RlglPhaseState()
    phase_state.enter("green", now=10.0)

    assert phase_state.elapsed(now=13.5) == 3.5


# ---------------------------------------------------------------------------
# stop_music -- stop-and-clear the nullable music receipt
# ---------------------------------------------------------------------------


def test_stop_music_stops_and_clears_the_receipt():
    """stop_music() requests the effect stop and drops the reference."""
    phase_state = RlglPhaseState()
    receipt = EffectReceipt(1)
    phase_state.music_receipt = receipt

    phase_state.stop_music()

    assert receipt.is_stopped()
    assert phase_state.music_receipt is None


def test_stop_music_is_a_no_op_when_nothing_is_playing():
    """stop_music() does nothing (and does not raise) when music_receipt is None."""
    phase_state = RlglPhaseState()

    phase_state.stop_music()

    assert phase_state.music_receipt is None


# ---------------------------------------------------------------------------
# rlgl_phase_state -- get-or-create accessor
# ---------------------------------------------------------------------------


def test_rlgl_phase_state_caches_the_same_instance_across_calls():
    """Phase/level/receipt state must persist across ticks, so the accessor
    must return the same instance rather than rebuilding it each time."""
    state = _make_state()

    first = rlgl_phase_state(state)
    second = rlgl_phase_state(state)

    assert first is second
