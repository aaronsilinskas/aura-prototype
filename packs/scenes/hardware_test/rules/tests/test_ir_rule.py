"""Tests for HwTestIrRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.input import ButtonData, InputEvents
from engine.network import LINE, NetworkEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls, SpyNetworkControls
from packs.scenes.hardware_test.rules.helpers.flash import ir_flash
from packs.scenes.hardware_test.rules.helpers.phases import MODE_IR, MODE_RGB
from packs.scenes.hardware_test.rules.ir_rule import HW_TEST_PAYLOAD, HwTestIrRule
from packs.scenes.hardware_test.rules.tests.helpers import seed_phase

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    mode=MODE_IR,
    network_spy: SpyNetworkControls | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy, network_controls=network_spy)
    rule = HwTestIrRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={})
    seed_phase(state, mode, entered=(mode is MODE_IR))
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(InputEvents.Sensors(ButtonData(states={"A": ButtonData.PRESSED})))
    engine.update(state)


def _fire_ir(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        NetworkEvents.IRReceived(b"test", signal_strength=0.9, error_margin=10, best_receiver=None)
    )
    engine.update(state)


# ---------------------------------------------------------------------------
# Entry effect
# ---------------------------------------------------------------------------


def test_entering_ir_sets_white_solid_on_all(spy):
    state, engine = _make_state(spy)
    seed_phase(state, MODE_IR, entered=False)
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)

    assert all(c[1] == "basic.solid" for c in spy.set_effect_calls)
    assert all(c[2] == {"color": 0xFFFFFF} for c in spy.set_effect_calls)
    assert any(c[0] == Scope.ALL for c in spy.set_effect_calls)


# ---------------------------------------------------------------------------
# IRReceived — no-op when not in IR mode
# ---------------------------------------------------------------------------


def test_ir_received_is_noop_when_mode_is_rgb(spy):
    state, engine = _make_state(spy, mode=MODE_RGB)
    _fire_ir(state, engine)
    assert spy.set_effect_calls == []
    assert ir_flash.key not in state


# ---------------------------------------------------------------------------
# IRReceived — fires flash when in IR mode
# ---------------------------------------------------------------------------


def test_ir_received_calls_set_effect_on_directional_with_white_solid(spy):
    state, engine = _make_state(spy)
    _fire_ir(state, engine)
    assert len(spy.set_effect_calls) == 1
    scope, name, options = spy.set_effect_calls[0]
    assert scope is Scope.DIRECTIONAL
    assert name == "basic.solid"
    assert options == {"color": 0xFFFFFF}


def test_ir_received_writes_ir_flash_receipt_to_state(spy):
    state, engine = _make_state(spy)
    _fire_ir(state, engine)
    assert ir_flash(state).receipt is not None


def test_ir_received_writes_ir_flash_start_to_state(spy):
    state, engine = _make_state(spy)
    _fire_ir(state, engine)
    assert ir_flash(state).start_time == state.total


def test_ir_received_logs_payload_and_signal_quality(spy, capsys):
    state, engine = _make_state(spy)
    _fire_ir(state, engine)

    out = capsys.readouterr().out
    assert str(b"test") in out
    assert "0.9" in out
    assert "10" in out


# ---------------------------------------------------------------------------
# Button A (IR mode) — sends an IR packet + fires the sent cue
# ---------------------------------------------------------------------------


def test_button_a_in_ir_mode_sends_hw_test_payload_on_line_emitter(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, network_spy=network_spy)

    _press_a(state, engine)

    assert network_spy.send_ir_calls == [(HW_TEST_PAYLOAD, LINE)]


def test_button_a_in_ir_mode_fires_scene_sfx_test_on_personal_as_sent_cue(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, network_spy=network_spy)

    _press_a(state, engine)

    sfx_calls = [c for c in spy.set_effect_calls if c[1] == "scene.sfx_test"]
    assert len(sfx_calls) == 1
    assert sfx_calls[0][0] == Scope.PERSONAL
    assert sfx_calls[0][2] == {}


def test_button_a_in_ir_mode_logs_sending_ir_packet(spy, capsys):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, network_spy=network_spy)

    _press_a(state, engine)

    assert "sending IR packet" in capsys.readouterr().out


def test_button_a_in_ir_mode_does_not_queue_fake_ir_received_event(spy):
    network_spy = SpyNetworkControls()
    state, engine = _make_state(spy, network_spy=network_spy)

    captured_events = []

    class _Capture(GameRule):
        def handle_event(self, event, s):
            captured_events.append(event)

    engine.add_rules(_Capture())

    _press_a(state, engine)

    ir_events = [e for e in captured_events if isinstance(e, NetworkEvents.IRReceived)]
    assert ir_events == []


def test_button_a_in_non_ir_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, mode=MODE_RGB)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
