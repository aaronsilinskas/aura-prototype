"""Tests for TagPlayingRule — hitpoints, progress bar, and game-over transition."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_PLAYING,
    PHASE_READY,
    tag_phase,
)
from packs.scenes.tag.rules.helpers.tag_config import DEFAULT_MAX_AMMO, DEFAULT_STARTING_HITPOINTS
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.playing_rule import TagPlayingRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, StubTimer]:
    timer = StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagPlayingRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    seed_phase(state, PHASE_PLAYING)
    return state, engine, timer


def _tick(
    state: GameState, engine: GameEngine, timer: StubTimer, total: float, button_a: bool = False
) -> None:
    timer.total = total
    states: dict[str, int] = {}
    if button_a:
        states["A"] = ButtonData.PRESSED
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states=states)))
    engine.update(state)


def test_entering_playing_sets_starting_hitpoints(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).hitpoints == DEFAULT_STARTING_HITPOINTS


def test_entering_playing_sets_full_progress_bar_on_personal(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 2
    personal_calls = [c for c in progress_calls if c[0] is Scope.PERSONAL]
    assert len(personal_calls) == 1
    _, _, options = personal_calls[0]
    assert options == {"progress": 1.0}


def test_entering_playing_stores_progress_receipt(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).progress_receipt is not None


def test_entering_playing_sets_starting_ammo(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).shot.ammo == DEFAULT_MAX_AMMO


def test_entering_playing_sets_full_ammo_bar_on_global_buff(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    buff_calls = [c for c in progress_calls if c[0] is Scope.Global.BUFF]
    assert len(buff_calls) == 1
    _, _, options = buff_calls[0]
    assert options == {"progress": 1.0}


def test_entering_playing_stores_ammo_receipt(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).ammo_receipt is not None


def test_exiting_playing_stops_ammo_bar(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)

    assert tag_phase(state).phase == PHASE_GAME_OVER
    assert tag.ammo_receipt is None


def test_non_playing_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    seed_phase(state, PHASE_READY, entered=True)

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []


def test_hitpoints_reaching_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)

    assert tag_phase(state).phase == PHASE_GAME_OVER


def test_hitpoints_dropping_below_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = -3

    _tick(state, engine, timer, 0.0)

    assert tag_phase(state).phase == PHASE_GAME_OVER


def test_positive_hitpoints_does_not_transition_to_game_over(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_phase(state).phase == PHASE_PLAYING
