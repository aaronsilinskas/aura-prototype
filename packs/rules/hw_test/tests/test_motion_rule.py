"""Tests for HwTestMotionRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from packs.rules.hw_test.motion_rule import (
    ACCEL_MAX,
    X_NEG_COLOR,
    X_POS_COLOR,
    Y_NEG_COLOR,
    Y_POS_COLOR,
    Z_NEG_COLOR,
    Z_POS_COLOR,
    HwTestMotionRule,
)
from packs.rules.hw_test.tests.helpers import SpyEffectControls

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(spy: SpyEffectControls, hw_mode: int) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy)
    rule = HwTestMotionRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={"hw_mode": hw_mode})
    return state, engine


def _fire(state: GameState, engine: GameEngine, acceleration: AccelerationData | None) -> None:
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={}), acceleration))
    engine.update(state)


# ---------------------------------------------------------------------------
# No-op when not IMU mode
# ---------------------------------------------------------------------------


def test_motion_rule_is_noop_when_hw_mode_is_0(spy):
    state, engine = _make_state(spy, hw_mode=0)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))
    assert spy.set_effect_calls == []


def test_motion_rule_is_noop_when_hw_mode_is_2(spy):
    state, engine = _make_state(spy, hw_mode=2)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))
    assert spy.set_effect_calls == []


def test_motion_rule_is_noop_when_hw_mode_is_3(spy):
    state, engine = _make_state(spy, hw_mode=3)
    _fire(state, engine, AccelerationData(z=ACCEL_MAX))
    assert spy.set_effect_calls == []


def test_motion_rule_is_noop_when_acceleration_is_none(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, None)
    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# X-axis
# ---------------------------------------------------------------------------


def test_x_axis_max_positive_sets_brightness_1_0_red_on_personal(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, name, options = x_calls[0]
    assert name == "basic.solid"
    assert options == {"color": X_POS_COLOR, "brightness": 1.0}
    assert X_POS_COLOR == 0xFF0000


def test_x_axis_max_negative_sets_brightness_1_0_cyan_on_personal(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=-ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, _name, options = x_calls[0]
    assert options == {"color": X_NEG_COLOR, "brightness": 1.0}
    assert X_NEG_COLOR == 0x00FFFF


# ---------------------------------------------------------------------------
# Y-axis
# ---------------------------------------------------------------------------


def test_y_axis_max_positive_sets_brightness_1_0_green_on_directional(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(y=ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, name, options = y_calls[0]
    assert name == "basic.solid"
    assert options == {"color": Y_POS_COLOR, "brightness": 1.0}
    assert Y_POS_COLOR == 0x00FF00


def test_y_axis_max_negative_sets_brightness_1_0_magenta_on_directional(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(y=-ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, _name, options = y_calls[0]
    assert options == {"color": Y_NEG_COLOR, "brightness": 1.0}
    assert Y_NEG_COLOR == 0xFF00FF


# ---------------------------------------------------------------------------
# Z-axis
# ---------------------------------------------------------------------------


def test_z_axis_max_positive_sets_brightness_1_0_blue_on_global_all(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(z=ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, name, options = z_calls[0]
    assert name == "basic.solid"
    assert options == {"color": Z_POS_COLOR, "brightness": 1.0}
    assert Z_POS_COLOR == 0x0000FF


def test_z_axis_max_negative_sets_brightness_1_0_yellow_on_global_all(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(z=-ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, _name, options = z_calls[0]
    assert options == {"color": Z_NEG_COLOR, "brightness": 1.0}
    assert Z_NEG_COLOR == 0xFFFF00


# ---------------------------------------------------------------------------
# Zero acceleration — brightness clamps to 0.0
# ---------------------------------------------------------------------------


def test_zero_acceleration_on_all_axes_fires_three_effects(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=0.0, y=0.0, z=0.0))

    assert len(spy.set_effect_calls) == 3


def test_all_three_axes_fire_on_each_tick(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    scopes = [c[0] for c in spy.set_effect_calls]
    assert Scope.PERSONAL in scopes
    assert Scope.DIRECTIONAL in scopes
    assert Scope.Global.ALL in scopes
