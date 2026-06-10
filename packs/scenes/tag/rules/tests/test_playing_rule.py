"""Tests for TagPlayingRule — hitpoints, progress bar, and shot firing."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import (
    DEFAULT_STARTING_HITPOINTS,
    KEY_DEAFEN_UNTIL,
    KEY_DEAFEN_WINDOW,
    KEY_ENTERED,
    KEY_HITPOINTS,
    KEY_PHASE,
    PHASE_GAME_OVER,
    PHASE_PLAYING,
)
from packs.scenes.tag.rules.playing_rule import TagPlayingRule


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
    spy: SpyEffectControls,
    initial_data: dict | None = None,
    network_spy: SpyNetworkControls | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    timer = _StubTimer()
    engine = GameEngine(spy, network_controls=network_spy, timer=timer)  # pyright: ignore
    engine.add_rules(TagPlayingRule())
    data = {"tag_phase": PHASE_PLAYING}
    if initial_data:
        data.update(initial_data)
    state = engine.create_state(SceneControls(), initial_data=data)
    return state, engine, timer


def _tick(
    state: GameState, engine: GameEngine, timer: _StubTimer, total: float, button_a: bool = False
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

    assert state.get(KEY_HITPOINTS, None) == DEFAULT_STARTING_HITPOINTS


def test_entering_playing_sets_full_progress_bar_on_personal(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    scope, _, options = progress_calls[0]
    assert scope is Scope.PERSONAL
    assert options == {"progress": 1.0}


def test_button_a_sends_tag_data_payload_on_line_emitter(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.01, button_a=True)

    expected_payload = bytes(encode_tag_data(TagData(0, 1, 1)))
    assert network_spy.send_ir_calls == [(expected_payload, LINE)]


def test_button_a_logs_the_send(spy, capsys):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 0.01, button_a=True)

    assert "sending IR packet" in capsys.readouterr().out


def test_button_a_sets_deafen_deadline(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(
        spy, network_spy=network_spy, initial_data={KEY_DEAFEN_WINDOW: 0.1}
    )

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 1.0, button_a=True)

    assert state.get(KEY_DEAFEN_UNTIL, None) == pytest.approx(1.1)


def test_non_playing_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    state.set(KEY_PHASE, "ready")

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []


def test_hitpoints_reaching_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy, initial_data={KEY_HITPOINTS: 0, KEY_ENTERED: True})

    _tick(state, engine, timer, 0.0)

    assert state.get(KEY_PHASE, None) == PHASE_GAME_OVER


def test_hitpoints_dropping_below_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy, initial_data={KEY_HITPOINTS: -3, KEY_ENTERED: True})

    _tick(state, engine, timer, 0.0)

    assert state.get(KEY_PHASE, None) == PHASE_GAME_OVER


def test_transitioning_to_game_over_clears_entered_flag(spy):
    state, engine, timer = _make_state(spy, initial_data={KEY_HITPOINTS: 0, KEY_ENTERED: True})

    _tick(state, engine, timer, 0.0)

    assert state.get(KEY_ENTERED, True) is False


def test_positive_hitpoints_does_not_transition_to_game_over(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert state.get(KEY_PHASE, None) == PHASE_PLAYING
