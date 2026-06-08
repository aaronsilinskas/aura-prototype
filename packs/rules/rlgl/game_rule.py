"""Red Light Green Light game rule — six-phase state machine driven by
accelerometer and buttons.

Phase flow::

    PHASE_READY → PHASE_RED_WARNING → PHASE_RED
                                          ↓ timer       ↓ motion
                                   PHASE_GREEN_WARNING  PHASE_GAME_OVER
                                          ↓ timer              ↓ timer
                                     PHASE_GREEN          PHASE_READY
                                          ↓ timer  ↓ motion
                                   PHASE_RED_WARNING   PHASE_GAME_OVER

All durations are read from ``GameState`` (seeded by ``initial_data`` at scene
creation) so values can be tuned per scene without code changes.  All keys use
the ``rlgl_`` prefix.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule
from engine.input import AccelerationData, ButtonData, InputEvents
from engine.state import EffectReceipt, GameState, Scope
from packs.rules.rlgl.helpers.motion_detector import (
    GRAVITY_LOWPASS_BETA,
    GREEN_MIN_MOTION_THRESHOLD,
    MOTION_EMA_ALPHA,
    RED_MAX_MOTION_THRESHOLD,
    linear_magnitude,
    low_pass,
)

# ---------------------------------------------------------------------------
# Phase constants
# ---------------------------------------------------------------------------

PHASE_READY: Final = "ready"
PHASE_RED_WARNING: Final = "red_warning"
PHASE_RED: Final = "red"
PHASE_GREEN_WARNING: Final = "green_warning"
PHASE_GREEN: Final = "green"
PHASE_GAME_OVER: Final = "game_over"

# ---------------------------------------------------------------------------
# GameState key names  (all rlgl_ prefixed)
# ---------------------------------------------------------------------------

_KEY_PHASE: Final = "rlgl_phase"
_KEY_PHASE_START: Final = "rlgl_phase_start"

# Config keys — readable from GameState, overridable via initial_data
_KEY_WARNING_DURATION: Final = "rlgl_warning_duration"
_KEY_RED_DURATION: Final = "rlgl_red_duration"
_KEY_GREEN_DURATION: Final = "rlgl_green_duration"
_KEY_GAME_OVER_DURATION: Final = "rlgl_game_over_duration"
_KEY_GREEN_STILL_TIMEOUT: Final = "rlgl_green_still_timeout"
_KEY_LAST_MOTION_TIME: Final = "rlgl_last_motion_time"
_KEY_MOTION_SMOOTHING: Final = "rlgl_motion_smoothing"
_KEY_GRAVITY_BETA: Final = "rlgl_gravity_beta"
_KEY_MOTION_EMA: Final = "rlgl_motion_ema"
_KEY_GRAVITY_X: Final = "rlgl_gravity_x"
_KEY_GRAVITY_Y: Final = "rlgl_gravity_y"
_KEY_GRAVITY_Z: Final = "rlgl_gravity_z"
_KEY_AMBIENT_RECEIPT: Final = "rlgl_ambient_receipt"

# ---------------------------------------------------------------------------
# Default durations (seconds)
# ---------------------------------------------------------------------------

_DEFAULT_WARNING_DURATION: Final = 3.0
_DEFAULT_RED_DURATION: Final = 5.0
_DEFAULT_GREEN_DURATION: Final = 5.0
_DEFAULT_GAME_OVER_DURATION: Final = 3.0
_DEFAULT_GREEN_STILL_TIMEOUT: Final = 0.75
_DEFAULT_MOTION_SMOOTHING: Final = MOTION_EMA_ALPHA
_DEFAULT_GRAVITY_BETA: Final = GRAVITY_LOWPASS_BETA

# ---------------------------------------------------------------------------
# Phase entry helpers
# ---------------------------------------------------------------------------


def _enter_phase(state: GameState, phase: str) -> None:
    """Record the new phase and its start time, stop any ambient music left
    running by the previous phase, and drop the gravity estimate.

    Every ``_enter_*`` helper begins here, so a looping ambient effect can never
    leak across a transition.  The ``has`` guard makes the stop a no-op when
    nothing is playing (e.g. entering Ready at game start).  Clearing the gravity
    keys forces :func:`_update_motion` to re-seed from the first sample of the
    next phase rather than carrying a stale orientation across the transition.
    """
    state.set(_KEY_PHASE, phase)
    state.set(_KEY_PHASE_START, state.total)
    if state.has(_KEY_AMBIENT_RECEIPT):
        state.pop(_KEY_AMBIENT_RECEIPT, EffectReceipt).stop()
    state.delete(_KEY_GRAVITY_X)
    state.delete(_KEY_GRAVITY_Y)
    state.delete(_KEY_GRAVITY_Z)


def _enter_ready(state: GameState) -> None:
    _enter_phase(state, PHASE_READY)
    state.effect_controls.set_effect(Scope.ALL, "rlgl.ready", {"level": 3})


_WARNING_STING_OPTS: Final = {
    "start_color": 0x000000,
    "end_color": 0xFFFF00,
    "brighten_duration": 0.3,
    "on_duration": 0.4,
    "darken_duration": 0.3,
    "off_duration": 0.0,
}


def _enter_red_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_RED_WARNING)
    state.effect_controls.set_effect(Scope.ALL, "rlgl.warning_sting", _WARNING_STING_OPTS)


def _enter_red(state: GameState) -> None:
    _enter_phase(state, PHASE_RED)
    state.set(_KEY_MOTION_EMA, 0.0)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", {"color": 0xFF0000})
    receipt = state.effect_controls.add_effect(Scope.AMBIENT, "rlgl.red_light_music", {})
    state.set(_KEY_AMBIENT_RECEIPT, receipt)


def _enter_green_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN_WARNING)
    state.effect_controls.set_effect(Scope.ALL, "rlgl.warning_sting", _WARNING_STING_OPTS)


def _enter_green(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN)
    state.set(_KEY_LAST_MOTION_TIME, state.total)
    state.set(_KEY_MOTION_EMA, 0.0)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", {"color": 0x00FF00})
    receipt = state.effect_controls.add_effect(Scope.AMBIENT, "rlgl.green_light_music", {})
    state.set(_KEY_AMBIENT_RECEIPT, receipt)


def _enter_game_over(state: GameState) -> None:
    _enter_phase(state, PHASE_GAME_OVER)
    state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
    state.effect_controls.add_effect(Scope.ALL, "rlgl.game_over_sting", {})


# ---------------------------------------------------------------------------
# Motion tracking
# ---------------------------------------------------------------------------


def _update_motion(state: GameState, accel: AccelerationData) -> float:
    """Update the gravity estimate and rolling motion average; return the average.

    Gravity is tracked with a slow per-axis low-pass and subtracted as a vector,
    so motion reads the same in any orientation.  The residual magnitude is then
    smoothed for spike rejection: a lone spike cannot cross a threshold while
    sustained motion accumulates across ticks.

    The gravity estimate is cleared on every phase change (see
    :func:`_enter_phase`) and re-seeded from the first sample of the new phase,
    so it never starts at zero and never carries a stale orientation across a
    transition.
    """
    beta = state.get(_KEY_GRAVITY_BETA, _DEFAULT_GRAVITY_BETA)
    if state.has(_KEY_GRAVITY_X):
        gx = low_pass(state.get(_KEY_GRAVITY_X, accel.x), accel.x, beta)
        gy = low_pass(state.get(_KEY_GRAVITY_Y, accel.y), accel.y, beta)
        gz = low_pass(state.get(_KEY_GRAVITY_Z, accel.z), accel.z, beta)
    else:
        gx, gy, gz = accel.x, accel.y, accel.z
    state.set(_KEY_GRAVITY_X, gx)
    state.set(_KEY_GRAVITY_Y, gy)
    state.set(_KEY_GRAVITY_Z, gz)

    alpha = state.get(_KEY_MOTION_SMOOTHING, _DEFAULT_MOTION_SMOOTHING)
    linear = linear_magnitude(accel, gx, gy, gz)
    ema = low_pass(state.get(_KEY_MOTION_EMA, 0.0), linear, alpha)
    state.set(_KEY_MOTION_EMA, ema)
    return ema


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class RlglGameRule(GameRule):
    """Drives the Red Light Green Light six-phase state machine.

    All mutable state is kept in ``GameState`` under ``rlgl_`` keys.  The rule
    itself is stateless beyond the registered event handler.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if _KEY_PHASE not in state:
            _enter_ready(state)

        phase = state.get(_KEY_PHASE, PHASE_READY)
        phase_start = state.get(_KEY_PHASE_START, state.total)
        phase_elapsed = state.total - phase_start

        if phase == PHASE_READY:
            self._check_ready(event, state)
        elif phase == PHASE_RED_WARNING:
            self._check_red_warning(state, phase_elapsed)
        elif phase == PHASE_RED:
            self._check_red(event, state, phase_elapsed)
        elif phase == PHASE_GREEN_WARNING:
            self._check_green_warning(state, phase_elapsed)
        elif phase == PHASE_GREEN:
            self._check_green(event, state, phase_elapsed)
        elif phase == PHASE_GAME_OVER:
            self._check_game_over(state, phase_elapsed)

    def _check_ready(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        buttons = event.buttons.states
        a_pressed = buttons.get("A") == ButtonData.PRESSED
        b_pressed = buttons.get("B") == ButtonData.PRESSED
        if a_pressed or b_pressed:
            _enter_red_warning(state)

    def _check_red_warning(self, state: GameState, elapsed: float) -> None:
        duration = state.get(_KEY_WARNING_DURATION, _DEFAULT_WARNING_DURATION)
        if elapsed >= duration:
            _enter_red(state)

    def _check_red(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        elapsed: float,
    ) -> None:
        red_duration = state.get(_KEY_RED_DURATION, _DEFAULT_RED_DURATION)

        # Timer expiry is always checked before motion
        if elapsed >= red_duration:
            _enter_green_warning(state)
            return

        if event.acceleration is not None:
            ema = _update_motion(state, event.acceleration)
            if ema > RED_MAX_MOTION_THRESHOLD:
                _enter_game_over(state)

    def _check_green_warning(self, state: GameState, elapsed: float) -> None:
        duration = state.get(_KEY_WARNING_DURATION, _DEFAULT_WARNING_DURATION)
        if elapsed >= duration:
            _enter_green(state)

    def _check_green(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        elapsed: float,
    ) -> None:
        green_duration = state.get(_KEY_GREEN_DURATION, _DEFAULT_GREEN_DURATION)

        # Timer expiry is always checked before motion
        if elapsed >= green_duration:
            _enter_red_warning(state)
            return

        if event.acceleration is not None:
            ema = _update_motion(state, event.acceleration)
            if ema >= GREEN_MIN_MOTION_THRESHOLD:
                state.set(_KEY_LAST_MOTION_TIME, state.total)
            else:
                still_timeout = state.get(_KEY_GREEN_STILL_TIMEOUT, _DEFAULT_GREEN_STILL_TIMEOUT)
                last_motion = state.get(_KEY_LAST_MOTION_TIME, state.total)
                if state.total - last_motion >= still_timeout:
                    _enter_game_over(state)

    def _check_game_over(self, state: GameState, elapsed: float) -> None:
        duration = state.get(_KEY_GAME_OVER_DURATION, _DEFAULT_GAME_OVER_DURATION)
        if elapsed >= duration:
            _enter_ready(state)


RULE = RlglGameRule()
