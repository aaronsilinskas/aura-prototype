"""Tests for HwTestSfxRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hw_test.rules.sfx_rule import HwTestSfxRule

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, hw_mode: int) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    engine.add_rules(HwTestSfxRule())
    state = engine.create_state(SceneControls(), initial_data={"hw_mode": hw_mode})
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"A": ButtonData.PRESSED}))
    )
    engine.update(state)


# ---------------------------------------------------------------------------
# Button A in SFX mode
# ---------------------------------------------------------------------------


def test_button_a_fires_scene_sfx_test_on_personal(spy):
    state, engine = _make_state(spy, hw_mode=4)

    _press_a(state, engine)

    sfx_calls = [c for c in spy.set_effect_calls if c[1] == "scene.sfx_test"]
    assert len(sfx_calls) == 1
    assert sfx_calls[0][0] == Scope.PERSONAL
    assert sfx_calls[0][2] == {}


def test_button_a_logs_playing_sfx(spy, capsys):
    state, engine = _make_state(spy, hw_mode=4)

    _press_a(state, engine)

    assert "playing sfx" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Only reacts to Button A in SFX mode
# ---------------------------------------------------------------------------


def test_button_a_in_rgb_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, hw_mode=0)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_button_a_in_accelerometer_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, hw_mode=1)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_button_a_in_radio_mode_does_not_fire_sfx_test(spy):
    state, engine = _make_state(spy, hw_mode=3)

    _press_a(state, engine)

    assert spy.set_effect_calls == []


def test_non_a_press_in_sfx_mode_is_noop(spy):
    state, engine = _make_state(spy, hw_mode=4)

    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"B": ButtonData.PRESSED}))
    )
    engine.update(state)

    assert spy.set_effect_calls == []


def test_button_a_in_non_sfx_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, hw_mode=0)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
