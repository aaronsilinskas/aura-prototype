"""Tests for HwTestModeRule behaviour.

Per-mode Button A behaviour now lives in each mode's owning rule; those tests
live in ``test_rgb_rule.py``, ``test_motion_rule.py``, ``test_network_rule.py``,
and ``test_sfx_rule.py``. This file covers only what ``HwTestModeRule`` still
owns: one-time mode-entry effects, Button B advancement + flash-key cleanup,
mode-change logging, and flash expiry.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.mode_rule import FLASH_DURATION, HwTestModeRule


class _StubTimer:
    """Controllable timer for tests that need specific total values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls elapsed/total directly


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _press_button(state: GameState, button: str) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={button: ButtonData.PRESSED}))
    )


def _make_state_with_rule(
    spy: SpyEffectControls,
    initial_data: dict,
    timer: _StubTimer | None = None,
) -> tuple[GameState, GameEngine, HwTestModeRule]:
    engine = GameEngine(spy, timer=timer)
    rule = HwTestModeRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data=dict(initial_data))
    return state, engine, rule


# ---------------------------------------------------------------------------
# First-tick init
# ---------------------------------------------------------------------------


def test_first_tick_keeps_seeded_hw_mode(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 0


def test_entry_effects_fire_once_on_load_and_not_again_without_mode_change(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    assert spy.set_effect_calls  # entry effects fired on load

    # A second tick with no button press must not re-fire mode-entry effects.
    spy.set_effect_calls.clear()
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert spy.set_effect_calls == []


def test_button_b_logs_changing_to_new_mode(spy, capsys):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    capsys.readouterr()  # discard load output

    _press_button(state, "B")
    engine.update(state)

    assert "changing to mode 1" in capsys.readouterr().out


def test_first_tick_starts_rgb_idle_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    # Expect 5 set_effect calls for RGB mode entry
    names = [call[1] for call in spy.set_effect_calls]
    assert "elements.water" in names
    assert "elements.fire" in names
    assert "elements.lightning" in names
    assert "elements.earth" in names
    assert "elements.ice" in names


def test_first_tick_rgb_idle_effects_have_level_1_in_options(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    for _scope, name, options in spy.set_effect_calls:
        assert options.get("level") == 1, f"{name} expected level=1, got options={options}"


def test_first_tick_sets_rgb_level_in_state_data(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("rgb_level", None) == 1


def test_first_tick_accelerometer_mode_starts_progress_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 1})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 1
    names_and_options = [(call[1], call[2]) for call in spy.set_effect_calls]
    assert ("basic.progress", {"color": 0xFF0000, "progress": 0.0}) in names_and_options
    assert ("basic.progress", {"color": 0x00FF00, "progress": 0.0}) in names_and_options
    assert ("basic.progress", {"color": 0x0000FF, "progress": 0.0}) in names_and_options


def test_first_tick_ir_mode_starts_white_solid_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 2})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 2
    assert all(call[1] == "basic.solid" for call in spy.set_effect_calls)
    assert all(call[2] == {"color": 0xFFFFFF} for call in spy.set_effect_calls)


def test_first_tick_radio_mode_starts_white_solid_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 3})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 3
    assert all(call[1] == "basic.solid" for call in spy.set_effect_calls)
    assert all(call[2] == {"color": 0xFFFFFF} for call in spy.set_effect_calls)


# ---------------------------------------------------------------------------
# Button B — mode cycling
# ---------------------------------------------------------------------------


def test_button_b_advances_mode_from_rgb_to_accelerometer(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    # First tick initialises mode
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()

    _press_button(state, "B")
    engine.update(state)

    assert state.get("hw_mode", None) == 1


def test_button_b_cycles_mode_through_0_1_2_3_4_and_back_to_0(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    for expected_mode in [1, 2, 3, 4, 0]:
        _press_button(state, "B")
        engine.update(state)
        assert state.get("hw_mode", None) == expected_mode


def test_button_b_stops_all_effects_before_starting_new_mode(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.stop_effect_calls.clear()

    _press_button(state, "B")
    engine.update(state)

    assert spy.stop_effect_calls[0] is Scope.ALL


def test_button_b_clears_flash_keys_on_mode_change(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 2})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    state.set("ir_flash_receipt", object())
    state.set("ir_flash_start", 1.0)
    state.set("radio_flash_receipt", object())
    state.set("radio_flash_start", 1.0)

    _press_button(state, "B")
    engine.update(state)

    assert "ir_flash_receipt" not in state
    assert "ir_flash_start" not in state
    assert "radio_flash_receipt" not in state
    assert "radio_flash_start" not in state


# ---------------------------------------------------------------------------
# Flash expiry
# ---------------------------------------------------------------------------


def test_ir_flash_expires_and_restarts_directional_idle(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 2}, timer=timer)
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    receipt = EffectReceipt(42)
    state.set("ir_flash_receipt", receipt)
    state.set("ir_flash_start", 0.0)
    # Advance timer total beyond FLASH_DURATION
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert receipt.is_stopped()
    assert "ir_flash_receipt" not in state
    assert "ir_flash_start" not in state
    # Restarts DIRECTIONAL — at least one call for scope DIRECTIONAL
    directional_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(directional_calls) >= 1


def test_radio_flash_expires_and_restarts_global_all_idle(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 3}, timer=timer)
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    receipt = EffectReceipt(99)
    state.set("radio_flash_receipt", receipt)
    state.set("radio_flash_start", 0.0)
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert receipt.is_stopped()
    assert "radio_flash_receipt" not in state
    assert "radio_flash_start" not in state
    all_calls = [c for c in spy.set_effect_calls if c[0] in (Scope.Global.ALL, Scope.ALL)]
    assert len(all_calls) >= 1


def test_ir_flash_does_not_expire_before_duration(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 2}, timer=timer)
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    receipt = EffectReceipt(7)
    state.set("ir_flash_receipt", receipt)
    state.set("ir_flash_start", 0.0)
    timer.total = FLASH_DURATION - 0.01

    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert not receipt.is_stopped()
    assert "ir_flash_receipt" in state


# ---------------------------------------------------------------------------
# SFX mode (mode 4) — entry effect only; Button A behaviour lives in sfx_rule
# ---------------------------------------------------------------------------


def test_first_tick_sfx_mode_starts_cyan_solid_on_personal(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 4})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    personal_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(personal_calls) == 1
    assert personal_calls[0][1] == "basic.solid"
    assert personal_calls[0][2] == {"color": 0x00FFFF}


def test_enter_sfx_sets_only_personal_scope(spy):
    state, engine, _ = _make_state_with_rule(spy, {"hw_mode": 4})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    scopes = [c[0] for c in spy.set_effect_calls]
    assert all(s == Scope.PERSONAL for s in scopes)
