"""Tests for TagGameOverRule — fire + sting on entry, then back to Ready."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.game_over_rule import TagGameOverRule
from packs.scenes.tag.rules.helpers.phases import PHASE_GAME_OVER, PHASE_PLAYING, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.hit_rule import TagHitRule
from packs.scenes.tag.rules.playing_rule import TagPlayingRule
from packs.scenes.tag.rules.ready_rule import TagReadyRule
from packs.scenes.tag.rules.starting_rule import TagStartingRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls, initial_data: dict | None = None
) -> tuple[GameState, GameEngine, StubTimer]:
    timer = StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagGameOverRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    seed_phase(state, PHASE_GAME_OVER)
    return state, engine, timer


def _tick(state: GameState, engine: GameEngine, timer: StubTimer, total: float) -> None:
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

    assert tag_state(state).game_over_receipt is not None


def test_stays_in_game_over_while_sting_receipt_is_unstopped(spy):
    state, engine, timer = _make_state(spy)

    for total in [0.0, 1.0, 5.0, 50.0]:
        _tick(state, engine, timer, total)
        assert tag_state(state).phase == PHASE_GAME_OVER


def test_transitions_to_ready_when_sting_receipt_is_stopped(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, 0.0)

    receipt = tag_state(state).game_over_receipt
    assert receipt is not None
    receipt.stop()

    _tick(state, engine, timer, 1.0)

    assert tag_state(state).phase == PHASE_READY


def test_transitioning_to_ready_marks_phase_not_yet_entered(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, 0.0)

    receipt = tag_state(state).game_over_receipt
    receipt.stop()
    _tick(state, engine, timer, 1.0)

    assert tag_state(state).take_just_entered() is True


def test_non_game_over_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    seed_phase(state, "playing", entered=True)

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []
    assert spy.add_effect_calls == []


def test_full_loop_returns_to_playable_ready_after_hitpoints_reach_zero(spy):
    """Playing -> Game Over -> Ready closes the loop so a new game can start."""
    timer = StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagReadyRule(), TagPlayingRule(), TagGameOverRule())
    state = engine.create_state(SceneControls(), initial_data={})
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)
    assert tag_state(state).phase == PHASE_GAME_OVER

    receipt = tag_state(state).game_over_receipt
    assert receipt is not None
    receipt.stop()
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, 1.0)
    assert tag_state(state).phase == PHASE_READY

    spy.set_effect_calls.clear()
    _tick(state, engine, timer, 1.01)

    ready_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL


# ---------------------------------------------------------------------------
# Dispatch-order independence — the phase machine must give identical results
# regardless of which order the five rules are registered/dispatched in.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_order",
    [
        (TagReadyRule, TagPlayingRule, TagHitRule, TagStartingRule, TagGameOverRule),
        (TagGameOverRule, TagStartingRule, TagHitRule, TagPlayingRule, TagReadyRule),
        (TagHitRule, TagGameOverRule, TagReadyRule, TagStartingRule, TagPlayingRule),
    ],
)
def test_playing_to_game_over_transition_is_independent_of_rule_dispatch_order(spy, rule_order):
    timer = StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(*(cls() for cls in rule_order))
    state = engine.create_state(SceneControls(), initial_data={})
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.01)

    assert tag_state(state).phase == PHASE_GAME_OVER
    fire_calls = [c for c in spy.set_effect_calls if c[1] == "elements.fire"]
    assert len(fire_calls) == 1
    sting_calls = [c for c in spy.add_effect_calls if c[1] == "scene.game_over_sting"]
    assert len(sting_calls) == 1
    assert tag_state(state).game_over_receipt is not None
