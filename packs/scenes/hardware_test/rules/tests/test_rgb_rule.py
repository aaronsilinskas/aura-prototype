"""Tests for HwTestRgbRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.rgb_rule import HwTestRgbRule

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, hw_mode: int) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    engine.add_rules(HwTestRgbRule())
    state = engine.create_state(SceneControls(), initial_data={"hw_mode": hw_mode})
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"A": ButtonData.PRESSED}))
    )
    engine.update(state)


# ---------------------------------------------------------------------------
# Level cycling
# ---------------------------------------------------------------------------


def test_button_a_increments_level_from_1_to_2(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 1)

    _press_a(state, engine)

    assert state.get("rgb_level", None) == 2


def test_button_a_wraps_level_from_10_to_1(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 10)

    _press_a(state, engine)

    assert state.get("rgb_level", None) == 1


# ---------------------------------------------------------------------------
# Re-applies idle effects at the new level
# ---------------------------------------------------------------------------


def test_button_a_reapplies_idle_effects_on_all_five_scopes(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 1)

    _press_a(state, engine)

    assert len(spy.set_effect_calls) == 5


def test_button_a_passes_new_level_to_every_idle_effect(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 1)

    _press_a(state, engine)

    for _scope, _name, options in spy.set_effect_calls:
        assert options.get("level") == 2


def test_button_a_passes_wrapped_level_1_to_every_idle_effect(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 10)

    _press_a(state, engine)

    for _scope, _name, options in spy.set_effect_calls:
        assert options.get("level") == 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_button_a_logs_new_level(spy, capsys):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 1)

    _press_a(state, engine)

    assert "rgb level -> 2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Only reacts to Button A in RGB mode
# ---------------------------------------------------------------------------


def test_button_a_in_non_rgb_mode_is_noop(spy):
    state, engine = _make_state(spy, hw_mode=2)
    state.set("rgb_level", 1)

    _press_a(state, engine)

    assert spy.set_effect_calls == []
    assert state.get("rgb_level", None) == 1


def test_non_a_press_in_rgb_mode_is_noop(spy):
    state, engine = _make_state(spy, hw_mode=0)
    state.set("rgb_level", 1)

    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"B": ButtonData.PRESSED}))
    )
    engine.update(state)

    assert spy.set_effect_calls == []
    assert state.get("rgb_level", None) == 1


def test_button_a_in_non_rgb_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, hw_mode=1)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
