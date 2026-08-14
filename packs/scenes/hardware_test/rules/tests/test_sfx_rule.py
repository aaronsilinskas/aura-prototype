"""Tests for HwTestSfxRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.phases import (
    MODE_ACCELEROMETER,
    MODE_RADIO,
    MODE_RGB,
    MODE_SFX,
)
from packs.scenes.hardware_test.rules.sfx_rule import HwTestSfxRule
from packs.scenes.hardware_test.rules.tests.helpers import seed_phase

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, mode=MODE_SFX) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    engine.add_rules(HwTestSfxRule())
    state = engine.create_state(SceneControls(), initial_data={})
    seed_phase(state, mode, entered=(mode is MODE_SFX))
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(InputEvents.Sensors(ButtonData(states={"A": ButtonData.PRESSED})))
    engine.update(state)


# ---------------------------------------------------------------------------
# Entry effect
# ---------------------------------------------------------------------------


def test_entering_sfx_sets_cyan_solid_on_personal(spy):
    state, engine = _make_state(spy)
    seed_phase(state, MODE_SFX, entered=False)
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)

    personal_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(personal_calls) == 1
    assert personal_calls[0][1] == "basic.solid"
    assert personal_calls[0][2] == {"color": 0x00FFFF}


def test_entering_sfx_sets_only_personal_scope(spy):
    state, engine = _make_state(spy)
    seed_phase(state, MODE_SFX, entered=False)
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)

    scopes = [c[0] for c in spy.set_effect_calls]
    assert all(s == Scope.PERSONAL for s in scopes)


# ---------------------------------------------------------------------------
# Button A in SFX mode
# ---------------------------------------------------------------------------


def test_button_a_fires_scene_sfx_test_on_personal(spy):
    state, engine = _make_state(spy)

    _press_a(state, engine)

    sfx_calls = [c for c in spy.set_effect_calls if c[1] == "scene.sfx_test"]
    assert len(sfx_calls) == 1
    assert sfx_calls[0][0] == Scope.PERSONAL
    assert sfx_calls[0][2] == {}


def test_button_a_logs_playing_sfx(spy, capsys):
    state, engine = _make_state(spy)

    _press_a(state, engine)

    assert "playing sfx" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Only reacts to Button A in SFX mode
# ---------------------------------------------------------------------------


def test_button_a_in_rgb_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, mode=MODE_RGB)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_button_a_in_accelerometer_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, mode=MODE_ACCELEROMETER)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_button_a_in_radio_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, mode=MODE_RADIO)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_non_a_press_in_sfx_mode_is_noop(spy):
    state, engine = _make_state(spy)
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()

    state.queue_event(InputEvents.Sensors(ButtonData(states={"B": ButtonData.PRESSED})))
    engine.update(state)

    assert spy.set_effect_calls == []


def test_button_a_in_non_sfx_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, mode=MODE_RGB)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
