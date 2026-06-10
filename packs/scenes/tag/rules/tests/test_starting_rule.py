"""Tests for TagStartingRule — runs the warning countdown into Playing."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.tag.rules.helpers.phases import (
    KEY_PHASE,
    KEY_WARNING_PULSE_COUNT,
    KEY_WARNING_PULSE_DURATION,
    PHASE_PLAYING,
    PHASE_STARTING,
)
from packs.scenes.tag.rules.starting_rule import TagStartingRule


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
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    engine.add_rules(TagStartingRule())
    data = {"tag_phase": PHASE_STARTING}
    if initial_data:
        data.update(initial_data)
    state = engine.create_state(SceneControls(), initial_data=data)
    return state, engine, timer


def _tick(state: GameState, engine: GameEngine, timer: _StubTimer, total: float) -> None:
    timer.total = total
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)


def test_entering_starting_sets_looping_warning_pulse_once(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.01)

    warning_calls = [c for c in spy.set_effect_calls if c[1] == "scene.warning_pulse"]
    assert len(warning_calls) == 1
    assert warning_calls[0][0] is Scope.ALL


def test_transitions_to_playing_after_count_times_duration_seconds(spy):
    state, engine, timer = _make_state(
        spy, {KEY_WARNING_PULSE_COUNT: 5, KEY_WARNING_PULSE_DURATION: 0.6}
    )

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 2.9)
    assert state.get(KEY_PHASE, None) == PHASE_STARTING

    _tick(state, engine, timer, 3.0)
    assert state.get(KEY_PHASE, None) == PHASE_PLAYING


def test_transitioning_to_playing_stops_the_warning_pulse(spy):
    state, engine, timer = _make_state(
        spy, {KEY_WARNING_PULSE_COUNT: 1, KEY_WARNING_PULSE_DURATION: 0.1}
    )

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.1)

    assert spy.stop_effect_calls == [Scope.ALL]


def test_non_starting_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    state.set(KEY_PHASE, "ready")

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []
