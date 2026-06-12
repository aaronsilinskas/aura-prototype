"""Tests for TagShootingRule — Button-A firing and fire-shot feedback."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.network import LINE
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.rules.shooting_rule import TagShootingRule
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
    engine.add_rules(TagShootingRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    seed_phase(state, PHASE_PLAYING, entered=True)
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


def test_button_a_sends_tag_data_payload_on_line_emitter(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    expected_payload = bytes(encode_tag_data(TagData(0, 1, 1)))
    assert network_spy.send_ir_calls == [(expected_payload, LINE)]


def test_button_a_logs_the_send(spy, capsys):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    assert "sending IR packet" in capsys.readouterr().out


def test_button_a_sets_deafen_deadline(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(
        spy, network_spy=network_spy, initial_data={"tag_deafen_window": 0.1}
    )

    _tick(state, engine, timer, 1.0, button_a=True)

    assert tag_state(state).deafen_until == pytest.approx(1.1)


def test_button_a_plays_fire_shot_effect_on_directional(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0, button_a=True)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "scene.fire_shot"]
    assert len(fire_calls) == 1
    scope, _, _ = fire_calls[0]
    assert scope is Scope.DIRECTIONAL


def test_no_button_press_does_not_fire(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)

    _tick(state, engine, timer, 0.0)

    assert network_spy.send_ir_calls == []
    assert spy.set_effect_calls == []


def test_non_playing_phase_is_ignored(spy):
    network_spy = SpyNetworkControls()
    state, engine, timer = _make_state(spy, network_spy=network_spy)
    seed_phase(state, PHASE_READY, entered=True)

    _tick(state, engine, timer, 0.0, button_a=True)

    assert network_spy.send_ir_calls == []
    assert spy.set_effect_calls == []
