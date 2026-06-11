"""Tests for HwModeRule shared behaviour: entry effects, Button B advance,
mode cycling, and IR/radio flash expiry.

These tests register all five mode rules together (as the scene loader
would), since Button B advancement and entry effects depend on more than one
mode's rule seeing the same dispatch.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.flash import IR_FLASH_KEY, RADIO_FLASH_KEY, flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.helpers.phases import (
    MODE_ACCELEROMETER,
    MODE_IR,
    MODE_RADIO,
    MODE_RGB,
    MODE_SFX,
    hw_phase,
)
from packs.scenes.hardware_test.rules.ir_rule import HwTestIrRule
from packs.scenes.hardware_test.rules.motion_rule import HwTestMotionRule
from packs.scenes.hardware_test.rules.radio_rule import HwTestRadioRule
from packs.scenes.hardware_test.rules.rgb_rule import HwTestRgbRule
from packs.scenes.hardware_test.rules.sfx_rule import HwTestSfxRule
from packs.scenes.hardware_test.rules.tests.helpers import seed_phase


class _StubTimer:
    """Controllable timer for tests that need specific ``state.total`` values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls elapsed/total directly


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    timer: _StubTimer | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy, timer=timer)
    engine.add_rules(
        HwTestRgbRule(),
        HwTestMotionRule(),
        HwTestIrRule(),
        HwTestRadioRule(),
        HwTestSfxRule(),
    )
    state = engine.create_state(SceneControls(), initial_data={})
    return state, engine


def _tick(state: GameState, engine: GameEngine) -> None:
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={})))
    engine.update(state)


def _press_button(state: GameState, engine: GameEngine, button: str) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(ButtonData(states={button: ButtonData.PRESSED}))
    )
    engine.update(state)


# ---------------------------------------------------------------------------
# First-tick init
# ---------------------------------------------------------------------------


def test_starts_in_rgb_mode(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)

    assert hw_phase(state).phase is MODE_RGB


def test_entry_effects_fire_once_on_load_and_not_again_without_mode_change(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)
    assert spy.set_effect_calls  # entry effects fired on load

    # A second tick with no button press must not re-fire mode-entry effects.
    spy.set_effect_calls.clear()
    _tick(state, engine)

    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# Button B — mode cycling
# ---------------------------------------------------------------------------


def test_button_b_logs_changing_to_new_mode(spy, capsys):
    state, engine = _make_state(spy)
    _tick(state, engine)
    capsys.readouterr()  # discard load output

    _press_button(state, engine, "B")

    assert "changing to mode 1" in capsys.readouterr().out


def test_button_b_advances_mode_from_rgb_to_accelerometer(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)
    spy.set_effect_calls.clear()

    _press_button(state, engine, "B")

    assert hw_phase(state).phase is MODE_ACCELEROMETER


def test_button_b_cycles_mode_through_all_five_and_back_to_rgb(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)

    expected_order = [MODE_ACCELEROMETER, MODE_IR, MODE_RADIO, MODE_SFX, MODE_RGB]
    for expected_mode in expected_order:
        _press_button(state, engine, "B")
        assert hw_phase(state).phase is expected_mode


def test_button_b_stops_all_effects_before_starting_new_mode(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)
    spy.stop_effect_calls.clear()

    _press_button(state, engine, "B")

    assert spy.stop_effect_calls[0] is Scope.ALL


def test_button_b_clears_flash_keys_on_mode_change(spy):
    state, engine = _make_state(spy)
    seed_phase(state, MODE_IR, entered=True)
    _tick(state, engine)
    flash(state, IR_FLASH_KEY).restart(1.0, EffectReceipt(1))
    flash(state, RADIO_FLASH_KEY).restart(1.0, EffectReceipt(2))

    _press_button(state, engine, "B")

    assert IR_FLASH_KEY not in state
    assert RADIO_FLASH_KEY not in state


def test_advancing_to_new_mode_fires_its_entry_effect_in_the_same_tick(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)
    spy.set_effect_calls.clear()

    _press_button(state, engine, "B")

    # Accelerometer entry effect: three basic.progress bars.
    names = [c[1] for c in spy.set_effect_calls]
    assert names.count("basic.progress") == 3


# ---------------------------------------------------------------------------
# Flash expiry
# ---------------------------------------------------------------------------


def test_ir_flash_expires_and_restarts_directional_idle(spy):
    timer = _StubTimer()
    state, engine = _make_state(spy, timer=timer)
    seed_phase(state, MODE_IR, entered=True)
    _tick(state, engine)

    receipt = EffectReceipt(42)
    flash(state, IR_FLASH_KEY).restart(0.0, receipt)
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    _tick(state, engine)

    assert receipt.is_stopped()
    assert IR_FLASH_KEY not in state
    directional_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(directional_calls) >= 1


def test_radio_flash_expires_and_restarts_global_all_idle(spy):
    timer = _StubTimer()
    state, engine = _make_state(spy, timer=timer)
    seed_phase(state, MODE_RADIO, entered=True)
    _tick(state, engine)

    receipt = EffectReceipt(99)
    flash(state, RADIO_FLASH_KEY).restart(0.0, receipt)
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    _tick(state, engine)

    assert receipt.is_stopped()
    assert RADIO_FLASH_KEY not in state
    all_calls = [c for c in spy.set_effect_calls if c[0] in (Scope.Global.ALL, Scope.ALL)]
    assert len(all_calls) >= 1


def test_ir_flash_does_not_expire_before_duration(spy):
    timer = _StubTimer()
    state, engine = _make_state(spy, timer=timer)
    seed_phase(state, MODE_IR, entered=True)
    _tick(state, engine)

    receipt = EffectReceipt(7)
    flash(state, IR_FLASH_KEY).restart(0.0, receipt)
    timer.total = FLASH_DURATION - 0.01

    _tick(state, engine)

    assert not receipt.is_stopped()
    assert IR_FLASH_KEY in state
