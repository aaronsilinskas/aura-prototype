"""Tests for RlglGameRule behaviour — eight-phase state machine."""

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
    PHASE_LEVEL_UP,
    PHASE_READY,
    PHASE_RED,
    PHASE_RED_WARNING,
    PHASE_WIN,
    RULE,
    RlglGameRule,
)
from packs.rules.rlgl.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    RED_MAX_MOTION_THRESHOLD,
)

_G = AccelerationData.GRAVITY

# A device at rest reads only the gravity vector — zero motion once gravity is seeded.
_AT_REST = AccelerationData(x=0.0, y=0.0, z=_G)

# Held still on z, then deviated; relative to seeded gravity these read as the motion below.
_HIGH_ACCEL = AccelerationData(x=0.0, y=0.0, z=_G + 2.0)  # 2.0 m/s² of motion
_LOW_ACCEL = _AT_REST  # no motion


def _accel_with_mag(mag: float) -> AccelerationData:
    """Build a sample reading ``mag`` (m/s²) of motion above the gravity vector."""
    return AccelerationData(x=0.0, y=0.0, z=_G + mag)


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
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to RED phase.

    Uses zero-duration warning so the transition happens on the very next tick.
    Motion smoothing is disabled by default (``rlgl_motion_smoothing`` = 1.0) so a
    single sample registers immediately, and gravity tracking is frozen
    (``rlgl_gravity_beta`` = 0.0) so motion reads as the exact deviation from the
    seeded gravity vector; debounce tests override these explicitly.
    """
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_motion_smoothing": 1.0,
        "rlgl_gravity_beta": 0.0,
    }
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
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to GREEN phase.

    Uses zero-duration warning and red phases so transitions are immediate.
    Motion smoothing is disabled by default (``rlgl_motion_smoothing`` = 1.0) so a
    single sample registers immediately, and gravity tracking is frozen
    (``rlgl_gravity_beta`` = 0.0) so motion reads as the exact deviation from the
    seeded gravity vector; debounce tests override these explicitly.
    """
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_red_duration": 0.0,
        "rlgl_motion_smoothing": 1.0,
        "rlgl_gravity_beta": 0.0,
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


def _seed_gravity_at_rest(
    state: GameState,
    engine: GameEngine,
    timer: _StubTimer,
    total: float = 0.0,
) -> None:
    """Tick one at-rest sample so the gravity estimate is established before motion.

    Motion is measured relative to the tracked gravity vector, so a test must
    establish gravity (as if the device were held steady) before a deviation can
    register.  With gravity frozen (``rlgl_gravity_beta`` = 0.0 in the setup
    helpers) this pins it at the at-rest reading.
    """
    _tick(state, engine, timer, accel=_AT_REST, total=total)


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


def test_ready_shows_ready_effect_on_all_scopes(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    ready_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL


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


def test_button_press_from_ready_shows_yellow_warning_on_non_ambient_scopes(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    yellow_calls = [c for c in spy.set_effect_calls if c[2].get("end_color") == 0xFFFF00]
    assert len(yellow_calls) == 1
    assert yellow_calls[0][0] is Scope.NON_AMBIENT


def test_button_press_from_ready_uses_warning_sting_effect_for_warning(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    sting_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_calls) == 1
    assert sting_calls[0][0] is Scope.NON_AMBIENT


def test_red_warning_sting_uses_one_second_breathe_cycle(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)

    sting_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_calls) == 1
    opts = sting_calls[0][2]
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
    assert solid_calls[0][0] is Scope.NON_AMBIENT
    assert solid_calls[0][2]["color"] == 0xFF0000


# ---------------------------------------------------------------------------
# Red Light — motion gate and timer
# ---------------------------------------------------------------------------


def test_red_motion_ends_game_on_first_frame_with_no_grace_period(spy):
    """There is no grace window: once gravity is established, motion on the very
    first Red frame ends the game."""
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 0.0)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_red_lone_spike_does_not_trigger_game_over(spy):
    """A single noisy sample above threshold is smoothed away, not a game over."""
    # One spike at 1.5x threshold; with smoothing on, a lone sample must not trip the gate.
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_motion_smoothing": 0.5})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    spike = _accel_with_mag(RED_MAX_MOTION_THRESHOLD * 1.5)

    _tick(state, engine, timer, accel=spike, total=phase_start + 0.1)

    assert state.get("rlgl_phase", None) == PHASE_RED


def test_red_sustained_motion_triggers_game_over(spy):
    """Motion held across consecutive samples accumulates past the threshold."""
    # Same 1.5x-threshold motion as the lone-spike test, but sustained: it must be caught.
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_motion_smoothing": 0.5})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    motion = _accel_with_mag(RED_MAX_MOTION_THRESHOLD * 1.5)

    _tick(state, engine, timer, accel=motion, total=phase_start + 0.1)  # one sample: still safe
    _tick(state, engine, timer, accel=motion, total=phase_start + 0.2)  # held: now caught

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_red_motion_perpendicular_to_gravity_ends_game_like_aligned_motion(spy):
    """Orientation independence: with the device tilted, motion across the gravity
    axis ends the game just as motion along it would — no axis is privileged."""
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)
    tilted_rest = AccelerationData(x=_G, y=0.0, z=0.0)  # gravity resolved on x
    _tick(state, engine, timer, accel=tilted_rest, total=phase_start + 0.0)  # seed gravity

    moved = AccelerationData(x=_G, y=0.0, z=2.0)  # 2 m/s² perpendicular to gravity
    _tick(state, engine, timer, accel=moved, total=phase_start + 0.1)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_red_none_acceleration_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=None, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_RED


def test_red_timer_expiry_transitions_to_green_warning(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_red_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN_WARNING


def test_phase_change_clears_the_gravity_estimate(spy):
    """A phase transition drops the gravity estimate so the next phase re-seeds it
    from a fresh sample instead of carrying a stale orientation across."""
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_red_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    assert state.has("rlgl_gravity_x")  # established during Red

    _tick(state, engine, timer, total=phase_start + 3.0)  # RED → GREEN_WARNING

    assert not state.has("rlgl_gravity_x")


def test_red_timer_expiry_takes_priority_over_motion(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_red_duration": 3.0})
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


def test_green_warning_transition_uses_warning_sting_with_yellow_end_color(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    sting_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_calls) == 1
    assert sting_calls[0][0] is Scope.NON_AMBIENT
    assert sting_calls[0][2]["end_color"] == 0xFFFF00


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
    assert solid_calls[0][0] is Scope.NON_AMBIENT
    assert solid_calls[0][2]["color"] == 0x00FF00


# ---------------------------------------------------------------------------
# Green Light — motion gate and timer
# ---------------------------------------------------------------------------


def test_green_motion_below_threshold_for_less_than_still_timeout_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_still_timeout": 1.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 1.2)
    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 1.5)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_motion_above_threshold_resets_still_timer_so_brief_pause_is_forgiven(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_still_timeout": 1.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 1.5)
    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 1.9)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_sustained_stillness_for_still_timeout_triggers_game_over(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_still_timeout": 1.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_green_stillness_below_default_timeout_is_forgiven(spy):
    """With no override, stillness just under the 0.75s default keeps the game alive.

    ``_LOW_ACCEL`` reads as motionless regardless of the smoothing factor, so this
    exercises the still-timer alone.
    """
    state, engine, timer = _setup_green_phase(spy)  # default still-timeout
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 0.74)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_stillness_at_default_timeout_ends_game(spy):
    """With no override, stillness reaching the 0.75s default ends the game.

    Together with the forgiven-below test this locks ``_DEFAULT_GREEN_STILL_TIMEOUT``
    so a change to it is deliberate.
    """
    state, engine, timer = _setup_green_phase(spy)  # default still-timeout
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 0.75)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_green_lone_motion_spike_does_not_count_as_moving(spy):
    """A single sample isn't enough to register as moving, so stillness still wins."""
    # One spike at 1.5x the move threshold; with smoothing on it must not register as
    # moving, so the still-timer keeps running and expires.
    state, engine, timer = _setup_green_phase(
        spy,
        initial_data={"rlgl_motion_smoothing": 0.5, "rlgl_green_still_timeout": 1.0},
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    spike = _accel_with_mag(GREEN_MIN_MOTION_THRESHOLD * 1.5)

    _tick(state, engine, timer, accel=spike, total=phase_start + 1.5)

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER


def test_green_sustained_motion_registers_as_moving_and_resets_still_timer(spy):
    """Motion held across samples drives the average over the move threshold."""
    state, engine, timer = _setup_green_phase(
        spy,
        initial_data={
            "rlgl_motion_smoothing": 0.5,
            "rlgl_green_still_timeout": 2.0,
            "rlgl_green_duration": 10.0,
        },
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    motion = _accel_with_mag(GREEN_MIN_MOTION_THRESHOLD * 1.5)

    _tick(state, engine, timer, accel=motion, total=phase_start + 1.1)  # one sample: not yet
    _tick(state, engine, timer, accel=motion, total=phase_start + 1.2)  # held: now moving

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_none_acceleration_does_not_trigger_game_over(spy):
    state, engine, timer = _setup_green_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=None, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_GREEN


def test_green_timer_expiry_transitions_to_level_up_when_level_below_max(spy):
    """Green timer expiry at level 1 (below default max of 10) enters PHASE_LEVEL_UP."""
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP


def test_green_timer_expiry_takes_priority_over_motion(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 3.0)

    # Green expiry at level 1 (< max) goes to LEVEL_UP, not directly to RED_WARNING
    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP


# ---------------------------------------------------------------------------
# Game Over
# ---------------------------------------------------------------------------


def test_game_over_shows_fire_effect_on_all_scopes(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)

    fire_calls = [c for c in spy.set_effect_calls if c[1] == "elements.fire"]
    assert len(fire_calls) == 1
    assert fire_calls[0][0] is Scope.ALL


def test_game_over_transitions_to_ready_after_game_over_duration(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_game_over_duration": 2.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    go_start = state.get("rlgl_phase_start", 0.0)
    _tick(state, engine, timer, total=go_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_READY


def test_game_over_expiry_restores_ready_effect_on_all_scopes(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_game_over_duration": 2.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)
    go_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=go_start + 2.0)

    ready_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL


# ---------------------------------------------------------------------------
# Audio — Red Warning phase
# ---------------------------------------------------------------------------


def test_red_warning_sting_replaces_current_visual_not_layers_on_top(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING

    sting_add_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_add_calls) == 0


def test_red_warning_does_not_start_music(spy):
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING

    music_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.red_light_music"]
    assert len(music_calls) == 0


def test_red_warning_stops_music_receipt_from_green_phase(spy):
    state, engine, timer = _setup_green_phase(spy, initial_data={"rlgl_green_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    music_receipt = state.get("rlgl_music_receipt", None)
    assert music_receipt is not None

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → RED_WARNING

    assert music_receipt.is_stopped()
    assert not state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Audio — Red phase
# ---------------------------------------------------------------------------


def test_red_phase_starts_music_on_personal_scope(spy):
    state, engine, timer = _make_state(spy, initial_data={"rlgl_warning_duration": 0.0})
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED

    music_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.red_light_music"]
    assert len(music_calls) == 1
    assert music_calls[0][0] is Scope.PERSONAL


def test_red_phase_stores_music_receipt_in_game_state(spy):
    state, _engine, _timer = _setup_red_phase(spy)

    assert state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Audio — Green Warning phase
# ---------------------------------------------------------------------------


def test_green_warning_sets_warning_sting_on_non_ambient(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    sting_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_calls) == 1
    assert sting_calls[0][0] is Scope.NON_AMBIENT


def test_green_warning_sting_replaces_current_visual_not_layers_on_top(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    sting_add_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.warning_sting"]
    assert len(sting_add_calls) == 0


def test_green_warning_does_not_start_music(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    music_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.green_light_music"]
    assert len(music_calls) == 0


def test_green_warning_stops_music_receipt_from_red_phase(spy):
    state, engine, timer = _setup_red_phase(spy, initial_data={"rlgl_red_duration": 3.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    music_receipt = state.get("rlgl_music_receipt", None)
    assert music_receipt is not None

    _tick(state, engine, timer, total=phase_start + 3.0)  # RED → GREEN_WARNING

    assert music_receipt.is_stopped()
    assert not state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Audio — Green phase
# ---------------------------------------------------------------------------


def test_green_phase_starts_music_on_personal_scope(spy):
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED
    _tick(state, engine, timer, total=0.0)  # → GREEN_WARNING
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN

    music_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.green_light_music"]
    assert len(music_calls) == 1
    assert music_calls[0][0] is Scope.PERSONAL


def test_green_phase_stores_music_receipt_in_game_state(spy):
    state, _engine, _timer = _setup_green_phase(spy)

    assert state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Audio — Game Over phase
# ---------------------------------------------------------------------------


def test_game_over_plays_game_over_sting_on_all(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    sting_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.game_over_sting"]
    assert len(sting_calls) == 1
    assert sting_calls[0][0] is Scope.ALL


def test_game_over_stops_music_receipt(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    music_receipt = state.get("rlgl_music_receipt", None)
    assert music_receipt is not None

    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    assert music_receipt.is_stopped()


def test_game_over_removes_music_receipt_from_game_state(spy):
    state, engine, timer = _setup_red_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)
    _seed_gravity_at_rest(state, engine, timer, total=phase_start + 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    assert not state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Audio — Ready phase
# ---------------------------------------------------------------------------


def test_first_game_start_enters_ready_without_prior_music_receipt(spy):
    state, engine, timer = _make_state(spy)

    _tick(state, engine, timer, total=0.0)  # init → READY (no music receipt)

    assert state.get("rlgl_phase", None) == PHASE_READY
    assert not state.has("rlgl_music_receipt")


# ---------------------------------------------------------------------------
# Game Level — initialisation on game start
# ---------------------------------------------------------------------------


def test_game_start_sets_rlgl_level_to_1(spy):
    """``_start_game`` sets ``rlgl_level`` to 1 in GameState."""
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)  # init → READY

    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING via _start_game

    assert state.get("rlgl_level", None) == 1


def test_game_start_sets_ambient_progress_bar_to_one_over_max_level(spy):
    """``_start_game`` sets ``basic.progress`` on ``Scope.AMBIENT`` with
    ``progress = 1 / max_level`` (default max_level=10)."""
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)  # init → READY
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → _start_game

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    assert progress_calls[0][0] is Scope.AMBIENT
    assert progress_calls[0][2]["progress"] == pytest.approx(1 / 10)


def test_game_start_respects_rlgl_max_level_config(spy):
    """``rlgl_max_level`` config key controls the denominator of the progress fraction."""
    state, engine, timer = _make_state(spy, initial_data={"rlgl_max_level": 5})
    _tick(state, engine, timer, total=0.0)  # init → READY
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → _start_game

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    assert progress_calls[0][2]["progress"] == pytest.approx(1 / 5)


def test_game_start_stores_level_receipt_in_game_state(spy):
    """``_start_game`` stores the AMBIENT bar receipt under ``rlgl_level_receipt``."""
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)  # init → READY

    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → _start_game

    assert state.has("rlgl_level_receipt")


def test_game_start_still_enters_red_warning_phase(spy):
    """``_start_game`` calls ``_enter_red_warning`` — the phase still becomes RED_WARNING."""
    state, engine, timer = _make_state(spy)
    _tick(state, engine, timer, total=0.0)  # init → READY

    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING

    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


# ---------------------------------------------------------------------------
# Game Level — AMBIENT bar persists across mid-game phase transitions
# ---------------------------------------------------------------------------


def test_level_receipt_persists_through_red_warning_to_red_transition(spy):
    """``_enter_phase`` does NOT stop ``rlgl_level_receipt``; it persists mid-game."""
    state, engine, timer = _make_state(spy, initial_data={"rlgl_warning_duration": 0.0})
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING (_start_game)

    level_receipt = state.get("rlgl_level_receipt", None)
    assert level_receipt is not None

    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED

    # Receipt object must still be present and not stopped
    assert state.has("rlgl_level_receipt")
    assert not level_receipt.is_stopped()


def test_level_receipt_persists_through_red_to_green_warning_transition(spy):
    """``rlgl_level_receipt`` survives the RED → GREEN_WARNING transition."""
    state, engine, timer = _make_state(
        spy, initial_data={"rlgl_warning_duration": 0.0, "rlgl_red_duration": 0.0}
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # → RED_WARNING
    _tick(state, engine, timer, total=0.0)  # → RED

    level_receipt = state.get("rlgl_level_receipt", None)
    assert level_receipt is not None

    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING

    assert state.has("rlgl_level_receipt")
    assert not level_receipt.is_stopped()


# ---------------------------------------------------------------------------
# Game Level — AMBIENT bar cleared on return to READY
# ---------------------------------------------------------------------------


def test_enter_ready_deletes_level_receipt_from_state(spy):
    """``_enter_ready`` deletes ``rlgl_level_receipt`` so the AMBIENT bar does not persist
    across a full game cycle (game over → ready)."""
    state, engine, timer = _make_state(
        spy,
        initial_data={
            "rlgl_warning_duration": 0.0,
            "rlgl_red_duration": 5.0,  # long enough that motion ends the game, not the timer
            "rlgl_game_over_duration": 0.0,
            "rlgl_motion_smoothing": 1.0,
            "rlgl_gravity_beta": 0.0,
        },
    )
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING (_start_game)
    assert state.has("rlgl_level_receipt")

    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, accel=_AT_REST, total=0.0)  # seed gravity
    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=0.0)  # motion → GAME_OVER
    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER

    _tick(state, engine, timer, total=0.0)  # GAME_OVER → READY (duration=0)
    assert state.get("rlgl_phase", None) == PHASE_READY

    assert not state.has("rlgl_level_receipt")


def _setup_level_up_phase(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to PHASE_LEVEL_UP.

    Uses zero-duration phases so transitions are immediate.  max_level defaults to
    10 so level < max_level at level 1, meaning green timer expiry enters LEVEL_UP.
    """
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_red_duration": 0.0,
        "rlgl_green_duration": 0.0,
        "rlgl_motion_smoothing": 1.0,
        "rlgl_gravity_beta": 0.0,
    }
    if initial_data:
        data.update(initial_data)
    state, engine, timer = _make_state(spy, initial_data=data)
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING (_start_game)
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
    _tick(state, engine, timer, total=0.0)  # GREEN → LEVEL_UP (green_duration=0, level<max)
    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP
    return state, engine, timer


def _setup_win_phase(
    spy: SpyEffectControls,
    initial_data: dict | None = None,
) -> tuple[GameState, GameEngine, _StubTimer]:
    """Advance to PHASE_WIN by starting at max_level=1 so the first green expiry wins."""
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_red_duration": 0.0,
        "rlgl_green_duration": 0.0,
        "rlgl_max_level": 1,
        "rlgl_motion_smoothing": 1.0,
        "rlgl_gravity_beta": 0.0,
    }
    if initial_data:
        data.update(initial_data)
    state, engine, timer = _make_state(spy, initial_data=data)
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING (_start_game)
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
    _tick(state, engine, timer, total=0.0)  # GREEN → WIN (green_duration=0, level==max)
    assert state.get("rlgl_phase", None) == PHASE_WIN
    return state, engine, timer


# ---------------------------------------------------------------------------
# PHASE_LEVEL_UP — green timer expiry when level < max_level
# ---------------------------------------------------------------------------


def test_green_timer_expiry_at_level_below_max_enters_level_up(spy):
    """Green timer expiry when level < max_level transitions to PHASE_LEVEL_UP."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 10}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP


def test_level_up_increments_rlgl_level(spy):
    """Entering PHASE_LEVEL_UP increments rlgl_level by 1."""
    state, _engine, _timer = _setup_level_up_phase(spy)

    assert state.get("rlgl_level", None) == 2


def test_level_up_updates_ambient_progress_bar(spy):
    """PHASE_LEVEL_UP sets basic.progress on Scope.AMBIENT with new_level / max_level."""
    state, engine, timer = _make_state(
        spy,
        initial_data={
            "rlgl_warning_duration": 0.0,
            "rlgl_red_duration": 0.0,
            "rlgl_green_duration": 0.0,
            "rlgl_max_level": 10,
        },
    )
    _tick(state, engine, timer, total=0.0)
    _tick(state, engine, timer, button_a=True, total=0.0)  # _start_game → level=1
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=0.0)  # GREEN → LEVEL_UP

    progress_calls = [c for c in spy.set_effect_calls if c[1] == "basic.progress"]
    assert len(progress_calls) == 1
    assert progress_calls[0][0] is Scope.AMBIENT
    assert progress_calls[0][2]["progress"] == pytest.approx(2 / 10)


def test_level_up_stores_level_receipt_in_game_state(spy):
    """PHASE_LEVEL_UP stores a new receipt under rlgl_level_receipt."""
    state, _engine, _timer = _setup_level_up_phase(spy)

    assert state.has("rlgl_level_receipt")


def test_level_up_plays_level_up_effect_on_non_ambient(spy):
    """PHASE_LEVEL_UP plays rlgl.level_up on Scope.NON_AMBIENT."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 10}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → LEVEL_UP

    level_up_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.level_up"]
    assert len(level_up_calls) == 1
    assert level_up_calls[0][0] is Scope.NON_AMBIENT


def test_level_up_stops_music_receipt_from_green_phase(spy):
    """_enter_level_up calls _enter_phase which stops music."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 10}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    music_receipt = state.get("rlgl_music_receipt", None)
    assert music_receipt is not None

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → LEVEL_UP

    assert music_receipt.is_stopped()
    assert not state.has("rlgl_music_receipt")


def test_level_up_transitions_to_red_warning_after_level_up_duration(spy):
    """PHASE_LEVEL_UP → PHASE_RED_WARNING after rlgl_level_up_duration."""
    state, engine, timer = _setup_level_up_phase(spy, initial_data={"rlgl_level_up_duration": 2.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 2.0)

    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_level_up_does_not_transition_before_level_up_duration(spy):
    """PHASE_LEVEL_UP waits the full rlgl_level_up_duration before advancing."""
    state, engine, timer = _setup_level_up_phase(spy, initial_data={"rlgl_level_up_duration": 2.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 1.9)

    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP


def test_level_up_default_duration_is_one_second(spy):
    """rlgl_level_up_duration defaults to 1.0s."""
    state, engine, timer = _setup_level_up_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 1.0)

    assert state.get("rlgl_phase", None) == PHASE_RED_WARNING


def test_motion_is_ignored_during_level_up(spy):
    """Motion events during PHASE_LEVEL_UP do not trigger game over."""
    state, engine, timer = _setup_level_up_phase(spy, initial_data={"rlgl_level_up_duration": 5.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 0.5)

    assert state.get("rlgl_phase", None) == PHASE_LEVEL_UP


def test_game_over_motion_during_green_does_not_increment_level(spy):
    """Level does NOT increment when game over is triggered by motion in green."""
    state, engine, timer = _setup_green_phase(
        spy,
        initial_data={
            "rlgl_green_still_timeout": 1.0,
            "rlgl_max_level": 10,
        },
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_LOW_ACCEL, total=phase_start + 2.0)  # → GAME_OVER

    assert state.get("rlgl_phase", None) == PHASE_GAME_OVER
    assert state.get("rlgl_level", None) == 1  # unchanged


# ---------------------------------------------------------------------------
# PHASE_WIN — green timer expiry when level == max_level
# ---------------------------------------------------------------------------


def test_green_timer_expiry_at_max_level_enters_win(spy):
    """Green timer expiry when level == max_level transitions to PHASE_WIN."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 1}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.0)

    assert state.get("rlgl_phase", None) == PHASE_WIN


def test_win_plays_lightning_on_all_scopes_with_level_7(spy):
    """PHASE_WIN sets elements.lightning with level=7 on Scope.ALL."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 1}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → WIN

    lightning_calls = [c for c in spy.set_effect_calls if c[1] == "elements.lightning"]
    assert len(lightning_calls) == 1
    assert lightning_calls[0][0] is Scope.ALL
    assert lightning_calls[0][2].get("level") == 7


def test_win_adds_win_sting_on_all_scopes(spy):
    """PHASE_WIN adds rlgl.win_sting on Scope.ALL."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 1}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.add_effect_calls.clear()

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → WIN

    win_calls = [c for c in spy.add_effect_calls if c[1] == "rlgl.win_sting"]
    assert len(win_calls) == 1
    assert win_calls[0][0] is Scope.ALL


def test_win_stops_music_receipt_from_green_phase(spy):
    """_enter_win calls _enter_phase which stops green music."""
    state, engine, timer = _setup_green_phase(
        spy, initial_data={"rlgl_green_duration": 3.0, "rlgl_max_level": 1}
    )
    phase_start = state.get("rlgl_phase_start", 0.0)
    music_receipt = state.get("rlgl_music_receipt", None)
    assert music_receipt is not None

    _tick(state, engine, timer, total=phase_start + 3.0)  # GREEN → WIN

    assert music_receipt.is_stopped()
    assert not state.has("rlgl_music_receipt")


def test_win_transitions_to_ready_after_win_duration(spy):
    """PHASE_WIN → PHASE_READY after rlgl_win_duration."""
    state, engine, timer = _setup_win_phase(spy, initial_data={"rlgl_win_duration": 4.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 4.0)

    assert state.get("rlgl_phase", None) == PHASE_READY


def test_win_does_not_transition_before_win_duration(spy):
    """PHASE_WIN waits the full rlgl_win_duration before returning to READY."""
    state, engine, timer = _setup_win_phase(spy, initial_data={"rlgl_win_duration": 4.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 3.9)

    assert state.get("rlgl_phase", None) == PHASE_WIN


def test_win_default_duration_is_four_seconds(spy):
    """rlgl_win_duration defaults to 4.0s."""
    state, engine, timer = _setup_win_phase(spy)
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, total=phase_start + 4.0)

    assert state.get("rlgl_phase", None) == PHASE_READY


def test_motion_is_ignored_during_win(spy):
    """Motion events during PHASE_WIN do not trigger game over."""
    state, engine, timer = _setup_win_phase(spy, initial_data={"rlgl_win_duration": 5.0})
    phase_start = state.get("rlgl_phase_start", 0.0)

    _tick(state, engine, timer, accel=_HIGH_ACCEL, total=phase_start + 0.5)

    assert state.get("rlgl_phase", None) == PHASE_WIN


def test_win_expiry_restores_ready_effect_on_all_scopes(spy):
    """After win expires, the ready effect is set on Scope.ALL."""
    state, engine, timer = _setup_win_phase(spy, initial_data={"rlgl_win_duration": 2.0})
    phase_start = state.get("rlgl_phase_start", 0.0)
    spy.set_effect_calls.clear()

    _tick(state, engine, timer, total=phase_start + 2.0)

    ready_calls = [c for c in spy.set_effect_calls if c[1] == "rlgl.ready"]
    assert len(ready_calls) == 1
    assert ready_calls[0][0] is Scope.ALL


# ---------------------------------------------------------------------------
# Full 10-round game reaches PHASE_WIN
# ---------------------------------------------------------------------------


def test_full_game_at_fast_config_reaches_win_phase(spy):
    """A complete 10-round game with zero-duration phases ends in PHASE_WIN."""
    data: dict = {
        "rlgl_warning_duration": 0.0,
        "rlgl_red_duration": 0.0,
        "rlgl_green_duration": 0.0,
        "rlgl_green_still_timeout": 999.0,  # disable stillness game-over
        "rlgl_level_up_duration": 0.0,
        "rlgl_max_level": 10,
        "rlgl_motion_smoothing": 1.0,
        "rlgl_gravity_beta": 0.0,
    }
    state, engine, timer = _make_state(spy, initial_data=data)
    _tick(state, engine, timer, total=0.0)  # init → READY
    _tick(state, engine, timer, button_a=True, total=0.0)  # READY → RED_WARNING (level=1)

    # Each of the first 9 rounds: GREEN expires → LEVEL_UP, then LEVEL_UP → RED_WARNING.
    # Round 10: GREEN expires → WIN (level 10 == max_level 10).  The final tick stays in
    # WIN because win_duration defaults to 4.0 s and elapsed is 0 at t=0.
    for _ in range(9):
        _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
        _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
        _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
        _tick(state, engine, timer, total=0.0)  # GREEN → LEVEL_UP
        _tick(state, engine, timer, total=0.0)  # LEVEL_UP → RED_WARNING

    # Round 10 (level == max_level): GREEN expires → WIN
    _tick(state, engine, timer, total=0.0)  # RED_WARNING → RED
    _tick(state, engine, timer, total=0.0)  # RED → GREEN_WARNING
    _tick(state, engine, timer, total=0.0)  # GREEN_WARNING → GREEN
    _tick(state, engine, timer, total=0.0)  # GREEN → WIN

    assert state.get("rlgl_phase", None) == PHASE_WIN
