"""Tests for ``RlglPhaseState`` -- Game Level and receipt state and the
``rlgl_phase_state`` get-or-create accessor."""

from __future__ import annotations

from engine.engine import GameEngine
from engine.state import EffectReceipt, SceneControls, StateSlot
from engine.tests.helpers import SpyEffectControls
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import (
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


def test_new_phase_state_starts_at_level_one_with_no_receipts():
    """A freshly constructed phase state begins at level 1 with no in-flight
    receipts -- the bootstrap state the Ready phase's first entry expects."""
    phase_state = RlglPhaseState()

    assert phase_state.level == 1
    assert phase_state.music_receipt is None
    assert phase_state.level_receipt is None
    assert phase_state.win_sting_receipt is None


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
    """Game Level and receipt state must persist across ticks, so the accessor
    must return the same instance rather than rebuilding it each time."""
    state = _make_state()

    first = rlgl_phase_state(state)
    second = rlgl_phase_state(state)

    assert first is second


def test_rlgl_phase_state_is_a_state_slot():
    """rlgl_phase_state must be a StateSlot so that the key, factory,
    and revalidate cast are owned in one place with no # type: ignore at
    call sites."""
    assert isinstance(rlgl_phase_state, StateSlot)
