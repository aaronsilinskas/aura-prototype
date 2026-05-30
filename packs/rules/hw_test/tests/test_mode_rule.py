"""Tests for HwTestModeRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.input import ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.version import Version
from packs.rules.hw_test.mode_rule import (
    FLASH_DURATION,
    HW_TEST_PAYLOAD,
    HwTestModeRule,
)
from packs.rules.hw_test.tests.helpers import SpyEffectControls


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


def test_first_tick_sets_hw_mode_from_initial_mode(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 0
    assert "initial_mode" not in state


def test_first_tick_starts_rgb_idle_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    # Expect 5 set_effect calls for RGB mode entry
    names = [call[1] for call in spy.set_effect_calls]
    assert "elements.water" in names
    assert "elements.fire" in names
    assert "elements.lightning" in names
    assert "elements.earth" in names
    assert "elements.ice" in names


def test_first_tick_sets_rgb_level_in_state_data(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("rgb_level", None) == 1


def test_first_tick_imu_mode_starts_solid_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 1})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 1
    names_and_options = [(call[1], call[3]) for call in spy.set_effect_calls]
    assert ("basic.solid", {"color": 0xFF0000}) in names_and_options
    assert ("basic.solid", {"color": 0x00FF00}) in names_and_options
    assert ("basic.solid", {"color": 0x0000FF}) in names_and_options


def test_first_tick_ir_mode_starts_white_solid_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 2})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 2
    assert all(call[1] == "basic.solid" for call in spy.set_effect_calls)
    assert all(call[3] == {"color": 0xFFFFFF} for call in spy.set_effect_calls)


def test_first_tick_radio_mode_starts_white_solid_effects(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 3})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert state.get("hw_mode", None) == 3
    assert all(call[1] == "basic.solid" for call in spy.set_effect_calls)
    assert all(call[3] == {"color": 0xFFFFFF} for call in spy.set_effect_calls)


# ---------------------------------------------------------------------------
# Button B — mode cycling
# ---------------------------------------------------------------------------


def test_button_b_advances_mode_from_rgb_to_imu(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    # First tick initialises mode
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()

    _press_button(state, "B")
    engine.update(state)

    assert state.get("hw_mode", None) == 1


def test_button_b_cycles_mode_through_0_1_2_3_and_back_to_0(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    for expected_mode in [1, 2, 3, 0]:
        _press_button(state, "B")
        engine.update(state)
        assert state.get("hw_mode", None) == expected_mode


def test_button_b_stops_all_effects_before_starting_new_mode(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.stop_effect_calls.clear()

    _press_button(state, "B")
    engine.update(state)

    assert spy.stop_effect_calls[0] is Scope.ALL


def test_button_b_clears_flash_keys_on_mode_change(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 2})
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
# Button A — per-mode behaviour
# ---------------------------------------------------------------------------


def test_button_a_in_rgb_mode_increments_level(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()

    _press_button(state, "A")
    engine.update(state)

    assert state.get("rgb_level", None) == 2


def test_button_a_in_rgb_mode_wraps_level_from_10_to_1(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    state.set("rgb_level", 10)
    spy.set_effect_calls.clear()

    _press_button(state, "A")
    engine.update(state)

    assert state.get("rgb_level", None) == 1


def test_button_a_in_rgb_mode_calls_set_effect_on_all_five_scopes(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 0})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()

    _press_button(state, "A")
    engine.update(state)

    # 5 set_effect calls — one per scope
    assert len(spy.set_effect_calls) == 5
    levels = {call[2] for call in spy.set_effect_calls}
    assert levels == {2}


def test_button_a_in_imu_mode_is_noop(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 1})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)
    spy.set_effect_calls.clear()
    spy.stop_effect_calls.clear()

    _press_button(state, "A")
    engine.update(state)

    assert spy.set_effect_calls == []
    assert spy.stop_effect_calls == []


def test_button_a_in_ir_mode_queues_ir_received_event(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 2})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    captured_events = []

    class _Capture(GameRule):
        def __init__(self):
            super().__init__("test.capture", Version(1, 0))

        def handle_event(self, event, s):
            captured_events.append(event)

    engine.add_rules(_Capture())

    _press_button(state, "A")
    engine.update(state)

    ir_events = [e for e in captured_events if isinstance(e, NetworkEvents.IRReceived)]
    assert len(ir_events) == 1
    assert ir_events[0].data == HW_TEST_PAYLOAD


def test_button_a_in_radio_mode_queues_radio_received_event(spy):
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 3})
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    captured_events = []

    class _Capture(GameRule):
        def __init__(self):
            super().__init__("test.capture", Version(1, 0))

        def handle_event(self, event, s):
            captured_events.append(event)

    engine.add_rules(_Capture())

    _press_button(state, "A")
    engine.update(state)

    radio_events = [e for e in captured_events if isinstance(e, NetworkEvents.RadioReceived)]
    assert len(radio_events) == 1
    assert radio_events[0].data == HW_TEST_PAYLOAD
    assert radio_events[0].sender == "local"


# ---------------------------------------------------------------------------
# Flash expiry
# ---------------------------------------------------------------------------


def test_ir_flash_expires_and_restarts_directional_idle(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 2}, timer=timer)
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
    # Restarts DIRECTIONAL at level 3
    directional_calls = [c for c in spy.set_effect_calls if c[2] == 3]
    assert len(directional_calls) >= 1


def test_radio_flash_expires_and_restarts_global_all_idle(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 3}, timer=timer)
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
    level_3_calls = [c for c in spy.set_effect_calls if c[2] == 3]
    assert len(level_3_calls) >= 1


def test_ir_flash_does_not_expire_before_duration(spy):
    timer = _StubTimer()
    state, engine, _ = _make_state_with_rule(spy, {"initial_mode": 2}, timer=timer)
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
