"""Tests for HwModeRule shared behaviour: entry effects, Button B advance,
mode cycling, and IR/radio flash expiry.

These tests register all six mode rules together (as the scene loader
would), since Button B advancement and entry effects depend on more than one
mode's rule seeing the same dispatch.
"""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import ButtonData, InputEvents
from engine.state import EffectReceipt, GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.flash import ir_flash, radio_flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.helpers.phases import (
    MODE_ACCELEROMETER,
    MODE_IR,
    MODE_MAGNETOMETER,
    MODE_RADIO,
    MODE_RGB,
    MODE_SFX,
    hw_phase,
)
from packs.scenes.hardware_test.rules.ir_rule import HwTestIrRule
from packs.scenes.hardware_test.rules.magnetic_rule import HwTestMagneticRule
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
    # Match SceneManager._resolve_rules: scene-local rules are added in
    # alphabetical order by module name (ir, magnetic, motion, radio, rgb,
    # sfx). Several tests below depend on this order to reproduce the same
    # dispatch sequence rules see in production within a single
    # PhaseMachine.enter() tick.
    engine.add_rules(
        HwTestIrRule(),
        HwTestMagneticRule(),
        HwTestMotionRule(),
        HwTestRadioRule(),
        HwTestRgbRule(),
        HwTestSfxRule(),
    )
    state = engine.create_state(SceneControls(), initial_data={})
    return state, engine


def _tick(state: GameState, engine: GameEngine) -> None:
    state.queue_event(InputEvents.Sensors(ButtonData(states={})))
    engine.update(state)


def _press_button(state: GameState, engine: GameEngine, button: str) -> None:
    state.queue_event(InputEvents.Sensors(ButtonData(states={button: ButtonData.PRESSED})))
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


def test_button_b_cycles_mode_through_all_six_and_back_to_rgb(spy):
    state, engine = _make_state(spy)
    _tick(state, engine)

    expected_order = [
        MODE_ACCELEROMETER,
        MODE_MAGNETOMETER,
        MODE_IR,
        MODE_RADIO,
        MODE_SFX,
        MODE_RGB,
    ]
    for expected_mode in expected_order:
        _press_button(state, engine, "B")
        assert hw_phase(state).phase is expected_mode


def test_button_b_logs_changing_to_magnetometer_from_accelerometer(spy, capsys):
    state, engine = _make_state(spy)
    _tick(state, engine)
    _press_button(state, engine, "B")  # RGB -> Accelerometer
    capsys.readouterr()  # discard prior output

    _press_button(state, engine, "B")  # Accelerometer -> Magnetometer

    assert "changing to mode 2" in capsys.readouterr().out


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
    ir_flash(state).restart(1.0, EffectReceipt(1))
    radio_flash(state).restart(1.0, EffectReceipt(2))

    _press_button(state, engine, "B")

    assert ir_flash.key not in state
    assert radio_flash.key not in state


def test_advancing_to_new_mode_fires_its_entry_effect_by_the_next_tick(spy):
    # With rules registered in production (alphabetical) order, motion_rule
    # (Accelerometer) is dispatched before rgb_rule for a given event, so a
    # Button-B advance from RGB to Accelerometer is observed by motion_rule
    # only on the *next* tick's dispatch (see PhaseMachine.enter /
    # take_just_entered). The entry effect must still fire exactly once, on
    # that next tick, with no extra prompting.
    state, engine = _make_state(spy)
    _tick(state, engine)
    spy.set_effect_calls.clear()

    _press_button(state, engine, "B")
    assert hw_phase(state).phase is MODE_ACCELEROMETER

    # Accelerometer entry effect: three basic.progress bars.
    names = [c[1] for c in spy.set_effect_calls]
    assert names.count("basic.progress") == 0

    spy.set_effect_calls.clear()
    _tick(state, engine)

    names = [c[1] for c in spy.set_effect_calls]
    assert names.count("basic.progress") == 3


def test_advancing_to_magnetometer_fires_its_entry_effect_by_the_next_tick(spy):
    # Same structural case as the Accelerometer entry test above, but for the
    # Accelerometer -> Magnetometer advance: magnetic_rule is dispatched
    # before motion_rule (alphabetical registration order), so while
    # motion_rule is still the active mode, magnetic_rule's own phase check
    # fails before it ever sees the AdvancedTo marker set during that same
    # dispatch. The entry effect still fires exactly once, on the next tick.
    state, engine = _make_state(spy)
    _tick(state, engine)  # RGB on_enter
    _press_button(state, engine, "B")  # RGB -> Accelerometer
    _tick(state, engine)  # Accelerometer on_enter (fires belatedly, see above)
    spy.set_effect_calls.clear()

    _press_button(state, engine, "B")  # Accelerometer -> Magnetometer
    assert hw_phase(state).phase is MODE_MAGNETOMETER

    # Magnetometer entry effect has not fired within this same dispatch.
    names = [c[1] for c in spy.set_effect_calls]
    assert names.count("basic.progress") == 0

    spy.set_effect_calls.clear()
    _tick(state, engine)

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
    ir_flash(state).restart(0.0, receipt)
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    _tick(state, engine)

    assert receipt.is_stopped()
    assert ir_flash.key not in state
    directional_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(directional_calls) >= 1


def test_radio_flash_expires_and_restarts_global_all_idle(spy):
    timer = _StubTimer()
    state, engine = _make_state(spy, timer=timer)
    seed_phase(state, MODE_RADIO, entered=True)
    _tick(state, engine)

    receipt = EffectReceipt(99)
    radio_flash(state).restart(0.0, receipt)
    timer.total = FLASH_DURATION + 0.01
    spy.set_effect_calls.clear()

    _tick(state, engine)

    assert receipt.is_stopped()
    assert radio_flash.key not in state
    all_calls = [c for c in spy.set_effect_calls if c[0] in (Scope.Global.ALL, Scope.ALL)]
    assert len(all_calls) >= 1


def test_ir_flash_does_not_expire_before_duration(spy):
    timer = _StubTimer()
    state, engine = _make_state(spy, timer=timer)
    seed_phase(state, MODE_IR, entered=True)
    _tick(state, engine)

    receipt = EffectReceipt(7)
    ir_flash(state).restart(0.0, receipt)
    timer.total = FLASH_DURATION - 0.01

    _tick(state, engine)

    assert not receipt.is_stopped()
    assert ir_flash.key in state
