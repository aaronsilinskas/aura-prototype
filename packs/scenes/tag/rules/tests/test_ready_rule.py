"""Tests for TagReadyRule — boots the scene to Ready and starts the game."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, PHASE_STARTING
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.ready_rule import TagReadyRule
from packs.scenes.tag.rules.tests.helpers import seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    engine.add_rules(TagReadyRule())
    state = engine.create_state(SceneControls(), initial_data={})
    return state, engine


def _tick(state: GameState, engine: GameEngine, button_a: bool = False) -> None:
    states: dict[str, int] = {}
    if button_a:
        states["A"] = ButtonData.PRESSED
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states=states)))
    engine.update(state)


def test_first_tick_with_no_phase_enters_ready_and_sets_ready_effect(spy):
    state, engine = _make_state(spy)

    _tick(state, engine)

    assert tag_state(state).phase == PHASE_READY
    ready_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL


def test_ready_effect_is_not_reissued_on_subsequent_ticks(spy):
    state, engine = _make_state(spy)

    _tick(state, engine)
    _tick(state, engine)

    ready_calls = [c for c in spy.set_effect_calls if c[1] == "scene.ready"]
    assert len(ready_calls) == 1


def test_button_press_in_ready_transitions_to_starting(spy):
    state, engine = _make_state(spy)

    _tick(state, engine)
    _tick(state, engine, button_a=True)

    assert tag_state(state).phase == PHASE_STARTING


def test_button_press_in_non_ready_phase_is_ignored(spy):
    state, engine = _make_state(spy)
    seed_phase(state, PHASE_STARTING, entered=True)

    _tick(state, engine, button_a=True)

    assert tag_state(state).phase == PHASE_STARTING
