"""Tests for HwTestRadioRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine, GameRule
from engine.input import ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.flash import radio_flash
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RADIO, MODE_RGB
from packs.scenes.hardware_test.rules.radio_rule import HW_TEST_PAYLOAD, HwTestRadioRule
from packs.scenes.hardware_test.rules.tests.helpers import seed_phase

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, mode=MODE_RADIO) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    rule = HwTestRadioRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={})
    seed_phase(state, mode, entered=(mode is MODE_RADIO))
    return state, engine


def _press_a(state: GameState, engine: GameEngine) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={"A": ButtonData.PRESSED}))
    )
    engine.update(state)


def _fire_radio(state: GameState, engine: GameEngine) -> None:
    state.queue_event(NetworkEvents.RadioReceived(b"test", "sender"))
    engine.update(state)


# ---------------------------------------------------------------------------
# Entry effect
# ---------------------------------------------------------------------------


def test_entering_radio_sets_white_solid_on_all(spy):
    state, engine = _make_state(spy)
    seed_phase(state, MODE_RADIO, entered=False)
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)

    assert all(c[1] == "basic.solid" for c in spy.set_effect_calls)
    assert all(c[2] == {"color": 0xFFFFFF} for c in spy.set_effect_calls)
    assert any(c[0] == Scope.ALL for c in spy.set_effect_calls)


# ---------------------------------------------------------------------------
# RadioReceived — no-op when not in Radio mode
# ---------------------------------------------------------------------------


def test_radio_received_is_noop_when_mode_is_rgb(spy):
    state, engine = _make_state(spy, mode=MODE_RGB)
    _fire_radio(state, engine)
    assert spy.set_effect_calls == []
    assert radio_flash.key not in state


# ---------------------------------------------------------------------------
# RadioReceived — fires flash when in Radio mode
# ---------------------------------------------------------------------------


def test_radio_received_calls_set_effect_on_global_all_with_white_solid(spy):
    state, engine = _make_state(spy)
    _fire_radio(state, engine)
    assert len(spy.set_effect_calls) == 1
    scope, name, options = spy.set_effect_calls[0]
    assert scope is Scope.Global.ALL
    assert name == "basic.solid"
    assert options == {"color": 0xFFFFFF}


def test_radio_received_writes_radio_flash_receipt_to_state(spy):
    state, engine = _make_state(spy)
    _fire_radio(state, engine)
    assert radio_flash(state).receipt is not None


def test_radio_received_writes_radio_flash_start_to_state(spy):
    state, engine = _make_state(spy)
    _fire_radio(state, engine)
    assert radio_flash(state).start_time == state.total


def test_radio_received_logs_payload_and_sender(spy, capsys):
    state, engine = _make_state(spy)
    state.queue_event(NetworkEvents.RadioReceived(b"payload-xyz", "device-7"))
    engine.update(state)

    out = capsys.readouterr().out
    assert str(b"payload-xyz") in out
    assert "device-7" in out


# ---------------------------------------------------------------------------
# Button A (Radio mode) — queues a simulated radio receive
# ---------------------------------------------------------------------------


def test_button_a_in_radio_mode_queues_radio_received_event(spy):
    state, engine = _make_state(spy)

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
    state, engine = _make_state(spy)

    _press_a(state, engine)

    assert "sending radio packet" in capsys.readouterr().out


def test_button_a_in_non_radio_mode_produces_no_log(spy, capsys):
    state, engine = _make_state(spy, mode=MODE_RGB)

    _press_a(state, engine)

    assert capsys.readouterr().out == ""
