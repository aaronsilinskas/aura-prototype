"""Tests for HwTestNetworkRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.network import NetworkEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.rules.hw_test.network_rule import HwTestNetworkRule

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, hw_mode: int) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    rule = HwTestNetworkRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={"hw_mode": hw_mode})
    return state, engine


def _fire_ir(state: GameState, engine: GameEngine) -> None:
    state.queue_event(NetworkEvents.IRReceived(b"test"))
    engine.update(state)


def _fire_radio(state: GameState, engine: GameEngine) -> None:
    state.queue_event(NetworkEvents.RadioReceived(b"test", "sender"))
    engine.update(state)


# ---------------------------------------------------------------------------
# IRReceived — no-op when hw_mode != 2
# ---------------------------------------------------------------------------


def test_ir_received_is_noop_when_hw_mode_is_0(spy):
    state, engine = _make_state(spy, hw_mode=0)
    _fire_ir(state, engine)
    assert spy.set_effect_calls == []
    assert "ir_flash_receipt" not in state
    assert "ir_flash_start" not in state


def test_ir_received_is_noop_when_hw_mode_is_1(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire_ir(state, engine)
    assert spy.set_effect_calls == []
    assert "ir_flash_receipt" not in state
    assert "ir_flash_start" not in state


def test_ir_received_is_noop_when_hw_mode_is_3(spy):
    state, engine = _make_state(spy, hw_mode=3)
    _fire_ir(state, engine)
    assert spy.set_effect_calls == []
    assert "ir_flash_receipt" not in state
    assert "ir_flash_start" not in state


# ---------------------------------------------------------------------------
# IRReceived — fires flash when hw_mode == 2
# ---------------------------------------------------------------------------


def test_ir_received_calls_set_effect_on_directional_with_white_solid(spy):
    state, engine = _make_state(spy, hw_mode=2)
    _fire_ir(state, engine)
    assert len(spy.set_effect_calls) == 1
    scope, name, options = spy.set_effect_calls[0]
    assert scope is Scope.DIRECTIONAL
    assert name == "basic.solid"
    assert options == {"color": 0xFFFFFF}


def test_ir_received_writes_ir_flash_receipt_to_state(spy):
    state, engine = _make_state(spy, hw_mode=2)
    _fire_ir(state, engine)
    assert isinstance(state.get("ir_flash_receipt", None), EffectReceipt)


def test_ir_received_writes_ir_flash_start_to_state(spy):
    state, engine = _make_state(spy, hw_mode=2)
    _fire_ir(state, engine)
    assert state.get("ir_flash_start", None) is not None


# ---------------------------------------------------------------------------
# RadioReceived — no-op when hw_mode != 3
# ---------------------------------------------------------------------------


def test_radio_received_is_noop_when_hw_mode_is_0(spy):
    state, engine = _make_state(spy, hw_mode=0)
    _fire_radio(state, engine)
    assert spy.set_effect_calls == []
    assert "radio_flash_receipt" not in state
    assert "radio_flash_start" not in state


def test_radio_received_is_noop_when_hw_mode_is_1(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire_radio(state, engine)
    assert spy.set_effect_calls == []
    assert "radio_flash_receipt" not in state
    assert "radio_flash_start" not in state


def test_radio_received_is_noop_when_hw_mode_is_2(spy):
    state, engine = _make_state(spy, hw_mode=2)
    _fire_radio(state, engine)
    assert spy.set_effect_calls == []
    assert "radio_flash_receipt" not in state
    assert "radio_flash_start" not in state


# ---------------------------------------------------------------------------
# RadioReceived — fires flash when hw_mode == 3
# ---------------------------------------------------------------------------


def test_radio_received_calls_set_effect_on_global_all_with_white_solid(spy):
    state, engine = _make_state(spy, hw_mode=3)
    _fire_radio(state, engine)
    assert len(spy.set_effect_calls) == 1
    scope, name, options = spy.set_effect_calls[0]
    assert scope is Scope.Global.ALL
    assert name == "basic.solid"
    assert options == {"color": 0xFFFFFF}


def test_radio_received_writes_radio_flash_receipt_to_state(spy):
    state, engine = _make_state(spy, hw_mode=3)
    _fire_radio(state, engine)
    assert isinstance(state.get("radio_flash_receipt", None), EffectReceipt)


def test_radio_received_writes_radio_flash_start_to_state(spy):
    state, engine = _make_state(spy, hw_mode=3)
    _fire_radio(state, engine)
    assert state.get("radio_flash_start", None) is not None
