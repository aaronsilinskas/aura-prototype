"""Tests for TagGameOverRule — fire + sting on entry, then back to Ready."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.game_over_rule import TagGameOverRule
from packs.scenes.tag.rules.helpers.phases import (
    KEY_ENTERED,
    KEY_GAME_OVER_RECEIPT,
    KEY_HITPOINTS,
    KEY_PHASE,
    PHASE_GAME_OVER,
    PHASE_PLAYING,
    PHASE_READY,
)
from packs.scenes.tag.rules.playing_rule import TagPlayingRule
from packs.scenes.tag.rules.ready_rule import TagReadyRule


class _StubTimer:
    """Controllable timer for tests that need specific total values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls, initial_data: dict | None = None
) -> tuple[GameState, GameEngine, _StubTimer]:
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagGameOverRule())
    data = {"tag_phase": PHASE_GAME_OVER}
    if initial_data:
        data.update(initial_data)
    state = engine.create_state(SceneControls(), initial_data=data)
    return state, engine, timer


def _tick(state: GameState, engine: GameEngine, timer: _StubTimer, total: float) -> None:
    timer.total = total
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)


def test_entering_game_over_plays_fire_on_all_scopes(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "elements.fire"]
    assert len(fire_calls) == 1
    assert fire_calls[0][0] is Scope.ALL


def test_entering_game_over_adds_sting_on_all_scopes(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    sting_calls = [c for c in spy.add_effect_calls if c[1] == "scene.game_over_sting"]
    assert len(sting_calls) == 1
    assert sting_calls[0][0] is Scope.ALL


def test_entering_game_over_stores_sting_receipt(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert state.has(KEY_GAME_OVER_RECEIPT)


def test_stays_in_game_over_while_sting_receipt_is_unstopped(spy):
    state, engine, timer = _make_state(spy)

    for total in [0.0, 1.0, 5.0, 50.0]:
        _tick(state, engine, timer, total)
        assert state.get(KEY_PHASE, None) == PHASE_GAME_OVER


def test_transitions_to_ready_when_sting_receipt_is_stopped(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, 0.0)

    receipt = state.get(KEY_GAME_OVER_RECEIPT, None)
    assert receipt is not None
    receipt.stop()

    _tick(state, engine, timer, 1.0)

    assert state.get(KEY_PHASE, None) == PHASE_READY


def test_transitioning_to_ready_clears_entered_flag(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, 0.0)

    receipt = state.get(KEY_GAME_OVER_RECEIPT, None)
    receipt.stop()
    _tick(state, engine, timer, 1.0)

    assert state.get(KEY_ENTERED, True) is False


def test_non_game_over_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    state.set(KEY_PHASE, "playing")

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []
    assert spy.add_effect_calls == []


def test_full_loop_returns_to_playable_ready_after_hitpoints_reach_zero(spy):
    """Playing -> Game Over -> Ready closes the loop so a new game can start."""
    timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagReadyRule(), TagPlayingRule(), TagGameOverRule())
    state = engine.create_state(
        SceneControls(),
        initial_data={
            KEY_PHASE: PHASE_PLAYING,
            KEY_ENTERED: True,
            KEY_HITPOINTS: 0,
        },
    )

    _tick(state, engine, timer, 0.0)
    assert state.get(KEY_PHASE, None) == PHASE_GAME_OVER

    receipt = state.get(KEY_GAME_OVER_RECEIPT, None)
    assert receipt is not None
    receipt.stop()
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, 1.0)
    assert state.get(KEY_PHASE, None) == PHASE_READY

    spy.set_effect_calls.clear()
    _tick(state, engine, timer, 1.01)

    ready_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL
