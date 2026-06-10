"""Tests for HwTestNetworkRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.input import ButtonData, InputEvents
from engine.network import LINE, NetworkEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from packs.scenes.hw_test.rules.network_rule import HW_TEST_PAYLOAD, HwTestNetworkRule

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    hw_mode: int,
    network_spy: SpyNetworkControls | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy, network_controls=network_spy)
    rule = HwTestNetworkRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={"hw_mode": hw_mode})
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"A": ButtonData.PRESSED}))
    )
    engine.update(state)


def _fire_ir(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        NetworkEvents.IRReceived(b"test", signal_strength=0.9, error_margin=10, best_receiver=None)
    )
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


# ---------------------------------------------------------------------------
# Button A (mode 2) — sends an IR packet + fires the sent cue
# ---------------------------------------------------------------------------


def test_button_a_in_ir_mode_sends_hw_test_payload_on_line_emitter(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, hw_mode=2, network_spy=network_spy)

    _press_a(state, engine)

    assert network_spy.send_ir_calls == [(HW_TEST_PAYLOAD, LINE)]


def test_button_a_in_ir_mode_fires_scene_sfx_test_on_personal_as_sent_cue(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, hw_mode=2, network_spy=network_spy)

    _press_a(state, engine)

    sfx_calls = [c for c in spy.set_effect_calls if c[1] == "scene.sfx_test"]
    assert len(sfx_calls) == 1
    assert sfx_calls[0][0] == Scope.PERSONAL
    assert sfx_calls[0][2] == {}


def test_button_a_in_ir_mode_logs_sending_ir_packet(spy, capsys):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, hw_mode=2, network_spy=network_spy)

    _press_a(state, engine)

    assert "sending IR packet" in capsys.readouterr().out


def test_button_a_in_ir_mode_does_not_queue_fake_ir_received_event(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, hw_mode=2, network_spy=network_spy)

    captured_events = []

    class _Capture(GameRule):
        def handle_event(self, event, s):
            captured_events.append(event)

    engine.add_rules(_Capture())

    _press_a(state, engine)

    ir_events = [e for e in captured_events if isinstance(e, NetworkEvents.IRReceived)]
    assert ir_events == []


# ---------------------------------------------------------------------------
# Button A (mode 3) — queues a simulated radio receive
# ---------------------------------------------------------------------------


def test_button_a_in_radio_mode_queues_radio_received_event(spy):
    state, engine = _make_state(spy, hw_mode=3)

    captured_events = []

    class _Capture(GameRule):
        def handle_event(self, event, s):
            captured_events.append(event)

    engine.add_rules(_Capture())

    _press_a(state, engine)

    radio_events = [e for e in captured_events if isinstance(e, NetworkEvents.RadioReceived)]
    assert len(radio_events) == 1
    assert radio_events[0].data == HW_TEST_PAYLOAD
    assert radio_events[0].sender == "local"


def test_button_a_in_radio_mode_logs_sending_radio_packet(spy, capsys):
    state, engine = _make_state(spy, hw_mode=3)

    _press_a(state, engine)

    assert "sending radio packet" in capsys.readouterr().out


def test_button_a_in_non_network_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, hw_mode=0)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Receive logging
# ---------------------------------------------------------------------------


def test_ir_received_logs_payload_and_signal_quality(spy, capsys):
    state, engine = _make_state(spy, hw_mode=2)
    _fire_ir(state, engine)

    out = capsys.readouterr().out
    assert str(b"test") in out
    assert "0.9" in out
    assert "10" in out


def test_radio_received_logs_payload_and_sender(spy, capsys):
    state, engine = _make_state(spy, hw_mode=3)
    state.queue_event(NetworkEvents.RadioReceived(b"payload-xyz", "device-7"))
    engine.update(state)

    out = capsys.readouterr().out
    assert str(b"payload-xyz") in out
    assert "device-7" in out
