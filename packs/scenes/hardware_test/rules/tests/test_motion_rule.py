"""Tests for HwTestMotionRule behaviour."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from engine.tests.helpers import SpyEffectControls
from packs.scenes.hardware_test.rules.helpers.phases import MODE_ACCELEROMETER, MODE_RGB
from packs.scenes.hardware_test.rules.motion_rule import (
    ACCEL_LOG_INTERVAL,
    ACCEL_MAX,
    HwTestMotionRule,
)
from packs.scenes.hardware_test.rules.tests.helpers import StubTimer, seed_phase

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    mode=MODE_ACCELEROMETER,
    timer: StubTimer | None = None,
) -> tuple[GameState, GameEngine]:
    engine = GameEngine(spy, timer=timer)
    rule = HwTestMotionRule()
    engine.add_rules(rule)
    state = engine.create_state(SceneControls(), initial_data={})
    seed_phase(state, mode, entered=(mode is MODE_ACCELEROMETER))
    return state, engine


def _fire(state: GameState, engine: GameEngine, acceleration: AccelerationData | None) -> None:
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states={}), acceleration))
    engine.update(state)


def _press_a(state: GameState, engine: GameEngine, acceleration: AccelerationData | None) -> None:
    state.queue_event(
        InputEvents.ButtonAndAcceleration(
            ButtonData(states={"A": ButtonData.PRESSED}), acceleration
        )
    )
    engine.update(state)


# ---------------------------------------------------------------------------
# No-op when not accelerometer mode
# ---------------------------------------------------------------------------


def test_motion_rule_is_noop_when_mode_is_rgb(spy):
    state, engine = _make_state(spy, mode=MODE_RGB)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))
    assert spy.set_effect_calls == []


def test_motion_rule_is_noop_when_acceleration_is_none(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, None)
    assert spy.set_effect_calls == []


# ---------------------------------------------------------------------------
# X-axis
# ---------------------------------------------------------------------------


def test_x_axis_max_positive_sets_red_progress_on_personal(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, _name, options = x_calls[0]
    assert options == {"color": 0xFF0000, "progress": pytest.approx(1.0)}


def test_x_axis_max_negative_sets_cyan_progress_on_personal(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=-ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 1
    _, _name, options = x_calls[0]
    assert options == {"color": 0x00FFFF, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Y-axis
# ---------------------------------------------------------------------------


def test_y_axis_max_positive_sets_green_progress_on_directional(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(y=ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, _name, options = y_calls[0]
    assert options == {"color": 0x00FF00, "progress": pytest.approx(1.0)}


def test_y_axis_max_negative_sets_magenta_progress_on_directional(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(y=-ACCEL_MAX))

    y_calls = [c for c in spy.set_effect_calls if c[0] == Scope.DIRECTIONAL]
    assert len(y_calls) == 1
    _, _name, options = y_calls[0]
    assert options == {"color": 0xFF00FF, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Z-axis
# ---------------------------------------------------------------------------


def test_z_axis_max_positive_sets_blue_progress_on_global_all(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(z=ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, _name, options = z_calls[0]
    assert options == {"color": 0x0000FF, "progress": pytest.approx(1.0)}


def test_z_axis_max_negative_sets_yellow_progress_on_global_all(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(z=-ACCEL_MAX))

    z_calls = [c for c in spy.set_effect_calls if c[0] == Scope.Global.ALL]
    assert len(z_calls) == 1
    _, _name, options = z_calls[0]
    assert options == {"color": 0xFFFF00, "progress": pytest.approx(1.0)}


# ---------------------------------------------------------------------------
# Effect name
# ---------------------------------------------------------------------------


def test_motion_rule_uses_basic_progress_effect_for_all_axes(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    names = [c[1] for c in spy.set_effect_calls]
    assert all(n == "basic.progress" for n in names)


# ---------------------------------------------------------------------------
# Progress scales with acceleration magnitude
# ---------------------------------------------------------------------------


def test_x_axis_half_max_acceleration_sets_progress_0_5(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX / 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["progress"] == pytest.approx(0.5)


def test_progress_clamps_to_1_0_when_acceleration_exceeds_max(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX * 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["progress"] == pytest.approx(1.0)


def test_zero_acceleration_yields_zero_progress(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=0.0, y=0.0, z=0.0))

    for _scope, _name, options in spy.set_effect_calls:
        assert options["progress"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# All three axes fire every tick
# ---------------------------------------------------------------------------


def test_all_three_axes_fire_on_first_tick(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    scopes = [c[0] for c in spy.set_effect_calls]
    assert Scope.PERSONAL in scopes
    assert Scope.DIRECTIONAL in scopes
    assert Scope.Global.ALL in scopes


def test_each_axis_fires_set_effect_every_tick(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))
    _fire(state, engine, AccelerationData(x=ACCEL_MAX / 2))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert len(x_calls) == 2
    assert x_calls[-1][2]["progress"] == pytest.approx(0.5)


def test_color_flips_with_sign_each_tick(spy):
    state, engine = _make_state(spy)
    _fire(state, engine, AccelerationData(x=ACCEL_MAX))
    _fire(state, engine, AccelerationData(x=-ACCEL_MAX))

    x_calls = [c for c in spy.set_effect_calls if c[0] == Scope.PERSONAL]
    assert x_calls[-1][2]["color"] == 0x00FFFF


# ---------------------------------------------------------------------------
# Button A is a no-op in accelerometer mode
# ---------------------------------------------------------------------------


def test_button_a_with_no_acceleration_is_noop(spy):
    state, engine = _make_state(spy)
    _press_a(state, engine, None)

    assert spy.set_effect_calls == []


def test_button_a_does_not_add_effects_beyond_the_three_axes(spy):
    state, engine = _make_state(spy)
    _press_a(state, engine, AccelerationData(x=ACCEL_MAX, y=ACCEL_MAX, z=ACCEL_MAX))

    # Only the three per-axis progress bars fire — Button A adds nothing.
    assert len(spy.set_effect_calls) == 3


# ---------------------------------------------------------------------------
# Throttled accelerometer logging (~2/sec)
# ---------------------------------------------------------------------------


def test_logs_xyz_on_first_matching_tick(spy, capsys):
    timer = StubTimer()
    state, engine = _make_state(spy, timer=timer)

    _fire(state, engine, AccelerationData(x=1.0, y=2.0, z=3.0))

    out = capsys.readouterr().out
    assert "accel" in out
    assert "1.0" in out and "2.0" in out and "3.0" in out


def test_does_not_log_again_before_interval_elapses(spy, capsys):
    timer = StubTimer()
    state, engine = _make_state(spy, timer=timer)

    timer.total = 0.0
    _fire(state, engine, AccelerationData(x=1.0))
    capsys.readouterr()  # discard first log

    timer.total = ACCEL_LOG_INTERVAL - 0.01
    _fire(state, engine, AccelerationData(x=1.0))

    assert capsys.readouterr().out == ""


def test_logs_again_after_interval_elapses(spy, capsys):
    timer = StubTimer()
    state, engine = _make_state(spy, timer=timer)

    timer.total = 0.0
    _fire(state, engine, AccelerationData(x=1.0))
    capsys.readouterr()  # discard first log

    timer.total = ACCEL_LOG_INTERVAL + 0.01
    _fire(state, engine, AccelerationData(x=1.0))

    assert "accel" in capsys.readouterr().out


def test_does_not_log_when_not_accelerometer_mode(spy, capsys):
    timer = StubTimer()
    state, engine = _make_state(spy, mode=MODE_RGB, timer=timer)

    _fire(state, engine, AccelerationData(x=1.0, y=2.0, z=3.0))

    assert capsys.readouterr().out == ""
