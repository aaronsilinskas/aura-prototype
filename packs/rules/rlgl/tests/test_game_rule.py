"""Tests for RlglGameRule behaviour — six-phase state machine."""

from __future__ import annotations

import pytest

from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.state import GameState, SceneControls, Scope
from packs.rules.hw_test.tests.helpers import SpyEffectControls
from packs.rules.rlgl.game_rule import (
    PHASE_GAME_OVER,
    PHASE_GREEN,
    PHASE_GREEN_WARNING,
    PHASE_READY,
    PHASE_RED,
    PHASE_RED_WARNING,
    RULE,
    RlglGameRule,
)

_G = AccelerationData.GRAVITY

# Produces motion above RED_MAX_MOTION_THRESHOLD (mag ≈ 2.0 > 1.5)
_HIGH_ACCEL = AccelerationData(x=0.0, y=0.0, z=_G + 2.0)

# Produces motion below GREEN_MIN_MOTION_THRESHOLD (mag = 0.0 < 1.0)
_LOW_ACCEL = AccelerationData(x=0.0, y=0.0, z=_G)


class _StubTimer:
    """Controllable timer for tests that need specific total values."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self.total: float = 0.0

    def update(self) -> None:
        pass  # Caller controls total directly


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def spy() -> SpyEffectControls:
    return SpyEffectControls()


def _make_state(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
    timer: _StubTimer | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    if timer is None:
        timer = _StubTimer()
    engine = GameEngine(spy, timer=timer)  # pyright: ignore[reportArgumentType]
    engine.add_rules(RlglGameRule())
    state = engine.create_state(SceneControls(), initial_data=initial_data or {})
    return state, engine, timer


def _tick(
    state: GameState,
    engine: GameEngine,
    timer: _StubTimer | None = None,
    accel: AccelerationData | None = None,
    button_a: bool = False,
    button_b: bool = False,
    total: float | None = None,
) -> None:
    """Queue one ButtonAndAcceleration event and advance one engine tick."""
    if total is not None and timer is not None:
        timer.total = total
    button_states: dict[str, int] = {}
    if button_a:
        button_states["A"] = ButtonData.PRESSED
    if button_b:
        button_states["B"] = ButtonData.PRESSED
    state.queue_event(InputEvents.ButtonAndAcceleration(ButtonData(states=button_states), accel))
    engine.update(state)


def _setup_red_phase(
    spy: SpyEffectControls,
    grace: float = 1.0,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to RED phase with configurable grace duration.

    Uses zero-duration warning so the transition happens on the very next tick.
    """
    data: dict = {"rlgl_warning_duration": 0.0, "rlgl_grace_duration": grace}
    if initial_data:
        data.update(initial_data)
    state, engine, timer = _make_state(spy, initial_data=data)
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED (duration=0)
    assert state.get("rlgl_phase", None) == PHASE_RED
    return state, engine, timer


def _setup_green_phase(
    spy: SpyEffectControls,
    grace: float = 1.0,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to GREEN phase with configurable grace duration.

    Uses zero-duration warning and red phases so transitions are immediate.
    """
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_red_duration": 0.0,
        "rlgl_grace_duration": grace,
    }
    if initial_data:
        data.update(initial_data)
    state, engine, timer = _make_state(spy, initial_data=data)
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
    assert state.get("rlgl_phase", None) == PHASE_GREEN
    return state, engine, timer


# ---------------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------------


def test_rule_singleton_is_exported():
    assert isinstance(RULE, RlglGameRule)


# ---------------------------------------------------------------------------
# First tick — initialisation
# ---------------------------------------------------------------------------


def test_first_tick_enters_ready_phase(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    assert state.get("rlgl_phase", None) == PHASE_READY


def test_ready_shows_water_effect_on_all_scopes(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    water_calls = [c for c in spy.set_effect_calls if c[1] == "elements.water"]
    assert len(water_calls) == 1
    assert water_calls[0][0] is Scope.ALL


def test_ready_shows_water_effect_at_level_3(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    water_calls = [c for c in spy.set_effect_calls if c[1] == "elements.water"]
    assert len(water_calls) == 1
    assert water_calls[0][2] == 3


# ---------------------------------------------------------------------------
# Ready — no transition without a button press
# ---------------------------------------------------------------------------


def test_ready_does_not_transition_without_button_press(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)

    for t in [1.0, 2.0, 5.0, 10.0]:
        _tick(state, engine, timer, total=t)

    assert state.get("rlgl_phase", None) == PHASE_READY


def test_ready_does_not_transition_on_high_acceleration(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=1.0)
    assert state.get("rlgl_phase", None) == PHASE_READY


# ---------------------------------------------------------------------------
# Ready → Red Warning on button press
# ---------------------------------------------------------------------------


def test_button_a_from_ready_enters_red_warning(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)
    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_button_b_from_ready_enters_red_warning(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_b=True, total=0.0)
    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_button_press_from_ready_shows_yellow_warning_on_all_scopes(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    yellow_calls = [c for c in spy.set_effect_calls if c[3].get("end_color") == 0xFFFF00]
    assert len(yellow_calls) == 1
    assert yellow_calls[0][0] is Scope.ALL


def test_button_press_from_ready_uses_pulse_effect_for_warning(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    pulse_calls = [c for c in spy.set_effect_calls if c[1] == "basic.pulse"]
    assert len(pulse_calls) == 1


def test_red_warning_pulse_uses_one_second_breathe_cycle(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    pulse_calls = [c for c in spy.set_effect_calls if c[1] == "basic.pulse"]
    assert len(pulse_calls) == 1
    opts = pulse_calls[0][3]
    assert opts["start_color"] == 0x000000
    assert opts["brighten_duration"] == 0.3
    assert opts["on_duration"] == 0.4
    assert opts["darken_duration"] == 0.3
    assert opts["off_duration"] == 0.0


# ---------------------------------------------------------------------------
# Red Warning → Red Light after warning duration
# ---------------------------------------------------------------------------


def test_red_warning_does_not_transition_before_warning_duration(spy):
    state, engine, timer = _make_state(spy, initial_data={"rlgl_warning_duration": 2.0})
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING at t=0

    _tick(state, engine, timer, total=1.9)
    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_red_warning_transitions_to_red_after_warning_duration(spy):
    state, engine, timer = _make_state(spy, initial_data={"rlgl_warning_duration": 2.0})
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING at t=0

    _tick(state, engine, timer, total=2.0)
    assert state.get("rlgl_phase", None) == PHASE_RED


def test_red_phase_transition_uses_solid_with_red_color(spy):
    state, engine, timer = _make_state(spy, initial_data={"rlgl_warning_duration": 0.0})
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED (duration=0)

    solid_calls = [c for c in spy.set_effect_calls if c[1] == "basic.solid"]
    assert len(solid_calls) == 1
    assert solid_calls[0][0] is Scope.ALL
    assert solid_calls[0][3]["color"] == 0xFF0000


# ---------------------------------------------------------------------------
# Red Light — motion gate and timer
# ---------------------------------------------------------------------------


def test_red_motion_above_threshold_within_grace_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_red_phase(spy, grace=2.0)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 1.0)

    assert state.get("rlgl_phase", None) == PHASE_RED


def test_red_motion_above_threshold_after_grace_triggers_game_over(spy):
    state, engine, timer = _setup_red_phase(spy, grace=1.0)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_red_none_acceleration_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_red_phase(spy, grace=1.0)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=None, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_RED


def test_red_timer_expiry_transitions_to_green_warning(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_red_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN_WARNING


def test_red_timer_expiry_takes_priority_over_motion(spy):
    state, engine, timer = _setup_red_phase(spy, grace=1.0, initial_data={"rlgl_red_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN_WARNING


def test_button_a_during_red_light_is_silently_ignored(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, button_a=True, total=phase_start + 0.5)

    assert state.get("rlgl_phase", None) == PHASE_RED


def test_button_b_during_red_light_is_silently_ignored(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, button_b=True, total=phase_start + 0.5)

    assert state.get("rlgl_phase", None) == PHASE_RED


# ---------------------------------------------------------------------------
# Green Warning → Green Light after warning duration
# ---------------------------------------------------------------------------


def test_green_warning_does_not_transition_before_warning_duration(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 2.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING at t=0
    _tick(state, engine, timer, total=2.0)  # RED_WARNING → RED (at t=2)
    _tick(state, engine, timer, total=2.0)  # RED → GREEN_WARNING at t=2

    _tick(state, engine, timer, total=3.9)

    assert state.get("rlgl_phase", None) == PHASE_GREEN_WARNING


def test_green_warning_transitions_to_green_after_warning_duration(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 2.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING at t=0
    _tick(state, engine, timer, total=2.0)  # RED_WARNING → RED (at t=2)
    _tick(state, engine, timer, total=2.0)  # RED → GREEN_WARNING at t=2

    _tick(state, engine, timer, total=4.0)  # elapsed=2.0 → GREEN
    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_warning_transition_uses_pulse_with_yellow_end_color(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    pulse_calls = [c for c in spy.set_effect_calls if c[1] == "basic.pulse"]
    assert len(pulse_calls) == 1
    assert pulse_calls[0][0] is Scope.ALL
    assert pulse_calls[0][3]["end_color"] == 0xFFFF00


def test_green_phase_transition_uses_solid_with_green_color(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    _tick(state, engine, timer, total=0.0)  # → GREEN_WARNING
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN

    solid_calls = [c for c in spy.set_effect_calls if c[1] == "basic.solid"]
    assert len(solid_calls) == 1
    assert solid_calls[0][0] is Scope.ALL
    assert solid_calls[0][3]["color"] == 0x00FF00


# ---------------------------------------------------------------------------
# Green Light — motion gate and timer
# ---------------------------------------------------------------------------


def test_green_motion_below_threshold_within_grace_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_green_phase(spy, grace=2.0)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 1.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_motion_below_threshold_for_less_than_still_timeout_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_green_phase(
        spy, grace=1.0, initial_data={"rlgl_green_still_timeout": 1.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 1.2)
    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 1.5)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_motion_above_threshold_resets_still_timer_so_brief_pause_is_forgiven(spy):
    state, engine, timer = _setup_green_phase(
        spy, grace=1.0, initial_data={"rlgl_green_still_timeout": 1.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 1.5)
    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 1.9)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_sustained_stillness_for_still_timeout_triggers_game_over(spy):
    state, engine, timer = _setup_green_phase(
        spy, grace=1.0, initial_data={"rlgl_green_still_timeout": 1.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_green_none_acceleration_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_green_phase(spy, grace=1.0)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=None, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_timer_expiry_transitions_to_red_warning(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_green_timer_expiry_takes_priority_over_motion(spy):
    state, engine, timer = _setup_green_phase(
        spy, grace=1.0, initial_data={"rlgl_green_duration": 3.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


# ---------------------------------------------------------------------------
# Game Over
# ---------------------------------------------------------------------------


def test_game_over_shows_fire_effect_on_all_scopes(spy):
    state, engine, timer = _setup_red_phase(spy, grace=1.0)
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "elements.fire"]
    assert len(fire_calls) == 1
    assert fire_calls[0][0] is Scope.ALL


def test_game_over_shows_fire_effect_at_level_10(spy):
    state, engine, timer = _setup_red_phase(spy, grace=1.0)
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "elements.fire"]
    assert len(fire_calls) == 1
    assert fire_calls[0][2] == 10


def test_game_over_transitions_to_ready_after_game_over_duration(spy):
    state, engine, timer = _setup_red_phase(
        spy, grace=1.0, initial_data={"rlgl_game_over_duration": 2.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    go_start = state.get("rlgl_phase_start", 0.0)
    _tick(state, engine, timer, total=go_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_READY


def test_game_over_expiry_restores_water_effect_on_all_scopes(spy):
    state, engine, timer = _setup_red_phase(
        spy, grace=1.0, initial_data={"rlgl_game_over_duration": 2.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)
    go_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=go_start + 2.0)

    water_calls = [c for c in spy.set_effect_calls if c[1] == "elements.water"]
    assert len(water_calls) == 1
    assert water_calls[0][0] is Scope.ALL


def test_game_over_expiry_restores_water_effect_at_level_3(spy):
    state, engine, timer = _setup_red_phase(
        spy, grace=1.0, initial_data={"rlgl_game_over_duration": 2.0}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)
    go_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=go_start + 2.0)

    water_calls = [c for c in spy.set_effect_calls if c[1] == "elements.water"]
    assert len(water_calls) == 1
    assert water_calls[0][2] == 3
