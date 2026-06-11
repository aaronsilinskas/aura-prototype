"""Tests for TagPlayingRule — hitpoints, progress bar, and shot firing."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_GAME_OVER, PHASE_PLAYING
from packs.scenes.tag.rules.helpers.tag_config import DEFAULT_STARTING_HITPOINTS
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.playing_rule import TagPlayingRule
from packs.scenes.tag.rules.tests.helpers import StubTimer, seed_phase


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
    network_spy: SpyNetworkControls | None = None,
) -> tuple[GameState, GameEngine, StubTimer]:
    timer = StubTimer()
    engine = GameEngine(spy, network_controls=network_spy, timer=timer)  # pyright: ignore
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
    assert len(progress_calls) == 1
    scope, _, options = progress_calls[0]
    assert scope is Scope.PERSONAL
    assert options == {"progress": 1.0}


def test_entering_playing_stores_progress_receipt(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).progress_receipt is not None


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
        spy, network_spy=network_spy, initial_data={"tag_deafen_window": 0.1}
    )

    _tick(state, engine, timer, 0.0)
    _tick(state, engine, timer, 1.0, button_a=True)

    assert tag_state(state).deafen_until == pytest.approx(1.1)


def test_non_playing_phase_is_ignored(spy):
    state, engine, timer = _make_state(spy)
    seed_phase(state, "ready", entered=True)

    _tick(state, engine, timer, 0.0)

    assert spy.set_effect_calls == []


def test_hitpoints_reaching_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).phase == PHASE_GAME_OVER


def test_hitpoints_dropping_below_zero_transitions_to_game_over(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = -3

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).phase == PHASE_GAME_OVER


def test_transitioning_to_game_over_marks_phase_not_yet_entered(spy):
    state, engine, timer = _make_state(spy)
    tag = seed_phase(state, PHASE_PLAYING, entered=True)
    tag.hitpoints = 0

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).just_entered is True


def test_positive_hitpoints_does_not_transition_to_game_over(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, 0.0)

    assert tag_state(state).phase == PHASE_PLAYING
