"""Tests for HwTestMotionRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from packs.rules.hw_test.motion_rule import ACCEL_MAX, HwTestMotionRule
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
# No-op when not accelerometer mode
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


def test_x_axis_max_positive_sets_red_progress_on_personal(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, _name, options = x_calls[0]
    assert options == {"color": 0xFF0000, "progress": pytest.approx(1.0)}


def test_x_axis_max_negative_sets_cyan_progress_on_personal(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=-ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, _name, options = x_calls[0]
    assert options == {"color": 0x00FFFF, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Y-axis
# ---------------------------------------------------------------------------


def test_y_axis_max_positive_sets_green_progress_on_directional(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(y=ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, _name, options = y_calls[0]
    assert options == {"color": 0x00FF00, "progress": pytest.approx(1.0)}


def test_y_axis_max_negative_sets_magenta_progress_on_directional(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(y=-ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, _name, options = y_calls[0]
    assert options == {"color": 0xFF00FF, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Z-axis
# ---------------------------------------------------------------------------


def test_z_axis_max_positive_sets_blue_progress_on_global_all(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(z=ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, _name, options = z_calls[0]
    assert options == {"color": 0x0000FF, "progress": pytest.approx(1.0)}


def test_z_axis_max_negative_sets_yellow_progress_on_global_all(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(z=-ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, _name, options = z_calls[0]
    assert options == {"color": 0xFFFF00, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Effect name
# ---------------------------------------------------------------------------


def test_motion_rule_uses_basic_progress_effect_for_all_axes(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    names = [c[1] for c in spy.set_effect_calls]
    assert all(n == "basic.progress" for n in names)


# ---------------------------------------------------------------------------
# Progress scales with acceleration magnitude
# ---------------------------------------------------------------------------


def test_x_axis_half_max_acceleration_sets_progress_0_5(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX / 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["progress"] == pytest.approx(0.5)


def test_progress_clamps_to_1_0_when_acceleration_exceeds_max(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX * 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["progress"] == pytest.approx(1.0)


def test_near_zero_axis_yields_near_zero_progress(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=0.0, y=0.0, z=0.0))

    for _scope, _name, options in spy.set_effect_calls:
        assert options["progress"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# All three axes fire every tick
# ---------------------------------------------------------------------------


def test_all_three_axes_fire_on_first_tick(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    scopes = [c[0] for c in spy.set_effect_calls]
    assert Scope.PERSONAL in scopes
    assert Scope.DIRECTIONAL in scopes
    assert Scope.Global.ALL in scopes


def test_each_axis_fires_set_effect_every_tick(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))
    _fire(state, engine, AccelerationData(x=ACCEL_MAX / 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 2
    assert x_calls[-1][2]["progress"] == pytest.approx(0.5)


def test_color_flips_with_sign_each_tick(spy):
    state, engine = _make_state(spy, hw_mode=1)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))
    _fire(state, engine, AccelerationData(x=-ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["color"] == 0x00FFFF
