"""Tests for HwTestRgbRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import GameState, SceneControls
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.phases import MODE_ACCELEROMETER, MODE_RGB
from packs.scenes.hardware_test.rules.rgb_rule import HwTestRgbRule
from packs.scenes.hardware_test.rules.tests.helpers import seed_phase

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, mode=MODE_RGB) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    engine.add_rules(HwTestRgbRule())
    state = engine.create_state(SceneControls(), initial_data={})
    if mode is not MODE_RGB:
        seed_phase(state, mode)
    return state, engine


def _tick(state: GameState, engine: GameEngine, button: str | None = None) -> None:
    states = {button: ButtonData.PRESSED} if button else {}
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states=states)))
    engine.update(state)


def _press_a(state: GameState, engine: GameEngine) -> None:
    _tick(state, engine, "A")


# ---------------------------------------------------------------------------
# Entry effects
# ---------------------------------------------------------------------------


def test_entering_rgb_sets_level_to_1(spy):
    state, engine = _make_state(spy)

    _tick(state, engine)

    assert state.get_or_none("rgb_level", int) == 1


def test_entering_rgb_applies_idle_effects_at_level_1(spy):
    state, engine = _make_state(spy)

    _tick(state, engine)

    names = [call[1] for call in spy.set_effect_calls]
    assert "elements.water" in names
    assert "elements.fire" in names
    assert "elements.lightning" in names
    assert "elements.earth" in names
    assert "elements.ice" in names
    for _scope, _name, options in spy.set_effect_calls:
        assert options.get("level") == 1


def test_entry_effects_fire_once_and_not_again_without_mode_change(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)
    assert spy.set_effect_calls  # entry effects fired on entry

    spy.set_effect_calls.clear()
    _tick(state, engine)

    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# Level cycling
# ---------------------------------------------------------------------------


def test_button_a_increments_level_from_1_to_2(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry

    _press_a(state, engine)

    assert state.get_or_none("rgb_level", int) == 2


def test_button_a_wraps_level_from_10_to_1(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry
    state.set("rgb_level", 10)

    _press_a(state, engine)

    assert state.get_or_none("rgb_level", int) == 1


# ---------------------------------------------------------------------------
# Re-applies idle effects at the new level
# ---------------------------------------------------------------------------


def test_button_a_reapplies_idle_effects_on_all_five_scopes(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry
    spy.set_effect_calls.clear()

    _press_a(state, engine)

    assert len(spy.set_effect_calls) == 5


def test_button_a_passes_new_level_to_every_idle_effect(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry
    spy.set_effect_calls.clear()

    _press_a(state, engine)

    for _scope, _name, options in spy.set_effect_calls:
        assert options.get("level") == 2


def test_button_a_passes_wrapped_level_1_to_every_idle_effect(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry
    state.set("rgb_level", 10)
    spy.set_effect_calls.clear()

    _press_a(state, engine)

    for _scope, _name, options in spy.set_effect_calls:
        assert options.get("level") == 1


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_button_a_logs_new_level(spy, capsys):
    state, engine = _make_state(spy)
    _tick(state, engine)  # consume entry
    capsys.readouterr()

    _press_a(state, engine)

    assert "rgb level -> 2" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Only reacts to Button A in RGB mode
# ---------------------------------------------------------------------------


def test_button_a_in_non_rgb_mode_is_noop(spy):
    state, engine = _make_state(spy, mode=MODE_ACCELEROMETER)

    _press_a(state, engine)

    assert spy.set_effect_calls == []
    assert "rgb_level" not in state


def test_button_a_in_non_rgb_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, mode=MODE_ACCELEROMETER)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
