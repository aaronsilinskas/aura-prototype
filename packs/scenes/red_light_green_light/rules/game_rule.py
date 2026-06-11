"""Red Light Green Light game rule — eight-phase state machine driven by
accelerometer and buttons.

Phase flow::

    PHASE_READY → PHASE_RED_WARNING → PHASE_RED
                                          ↓ timer          ↓ motion
                                   PHASE_GREEN_WARNING  PHASE_GAME_OVER
                                          ↓ timer               ↓ timer
                                     PHASE_GREEN           PHASE_READY
                                       ↓ timer (level<max)  ↓ motion
                                   PHASE_LEVEL_UP       PHASE_GAME_OVER
                                       ↓ timer
                                   PHASE_RED_WARNING

                                     PHASE_GREEN
                                       ↓ timer (level==max)
                                     PHASE_WIN
                                       ↓ timer
                                   PHASE_READY

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
from engine.input import AccelerationData, InputEvents
from engine.state import EffectReceipt, GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    RED_MAX_MOTION_THRESHOLD,
    linear_magnitude,
    low_pass,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config

# ---------------------------------------------------------------------------
# Phase constants
# ---------------------------------------------------------------------------

PHASE_READY: Final = "ready"
PHASE_RED_WARNING: Final = "red_warning"
PHASE_RED: Final = "red"
PHASE_GREEN_WARNING: Final = "green_warning"
PHASE_GREEN: Final = "green"
PHASE_LEVEL_UP: Final = "level_up"
PHASE_WIN: Final = "win"
PHASE_GAME_OVER: Final = "game_over"

# ---------------------------------------------------------------------------
# GameState key names  (all rlgl_ prefixed)
# ---------------------------------------------------------------------------

_KEY_PHASE: Final = "rlgl_phase"
_KEY_PHASE_START: Final = "rlgl_phase_start"

_KEY_LAST_MOTION_TIME: Final = "rlgl_last_motion_time"
_KEY_MOTION_EMA: Final = "rlgl_motion_ema"
_KEY_GRAVITY_X: Final = "rlgl_gravity_x"
_KEY_GRAVITY_Y: Final = "rlgl_gravity_y"
_KEY_GRAVITY_Z: Final = "rlgl_gravity_z"
_KEY_MUSIC_RECEIPT: Final = "rlgl_music_receipt"
_KEY_LEVEL: Final = "rlgl_level"
_KEY_LEVEL_RECEIPT: Final = "rlgl_level_receipt"
_KEY_WIN_STING_RECEIPT: Final = "rlgl_win_sting_receipt"

# ---------------------------------------------------------------------------
# Phase entry helpers
# ---------------------------------------------------------------------------


def _enter_phase(state: GameState, phase: str) -> None:
    """Record the new phase and its start time, stop any music left running by
    the previous phase, and drop the gravity estimate.

    Every ``_enter_*`` helper begins here, so a looping music effect can never
    leak across a transition.  The ``has`` guard makes the stop a no-op when
    nothing is playing (e.g. entering Ready at game start).  Clearing the gravity
    keys forces :func:`_update_motion` to re-seed from the first sample of the
    next phase rather than carrying a stale orientation across the transition.
    """
    state.set(_KEY_PHASE, phase)
    state.set(_KEY_PHASE_START, state.total)
    if state.has(_KEY_MUSIC_RECEIPT):
        state.pop(_KEY_MUSIC_RECEIPT, EffectReceipt).stop()
    state.delete(_KEY_GRAVITY_X)
    state.delete(_KEY_GRAVITY_Y)
    state.delete(_KEY_GRAVITY_Z)


def _enter_ready(state: GameState) -> None:
    _enter_phase(state, PHASE_READY)
    state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
    state.delete(_KEY_LEVEL_RECEIPT)


def _start_game(state: GameState) -> None:
    """Initialise a new game at level 1 and enter the Red Warning phase.

    Sets ``rlgl_level`` to 1, starts the ``Scope.AMBIENT`` progress bar at
    ``1 / max_level`` (denominator from ``rlgl_max_level``, default 10), stores
    the receipt under ``rlgl_level_receipt``, then hands off to
    ``_enter_red_warning``.  The level receipt persists across all mid-game
    phase transitions and is only cleared when ``_enter_ready`` is called.
    """
    state.set(_KEY_LEVEL, 1)
    max_level = rlgl_config(state).max_level
    receipt = state.effect_controls.set_effect(
        Scope.AMBIENT, "basic.progress", {"progress": 1 / max_level}
    )
    state.set(_KEY_LEVEL_RECEIPT, receipt)
    _enter_red_warning(state)


def _enter_red_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_RED_WARNING)
    level = state.get(_KEY_LEVEL, 1)
    state.effect_controls.set_effect(
        Scope.NON_AMBIENT, "scene.warning_sting", rlgl_config(state).warning_sting_opts(level)
    )


def _enter_red(state: GameState) -> None:
    _enter_phase(state, PHASE_RED)
    state.set(_KEY_MOTION_EMA, 0.0)
    state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0xFF0000})
    receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.red_light_music", {})
    state.set(_KEY_MUSIC_RECEIPT, receipt)


def _enter_green_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN_WARNING)
    level = state.get(_KEY_LEVEL, 1)
    state.effect_controls.set_effect(
        Scope.NON_AMBIENT, "scene.warning_sting", rlgl_config(state).warning_sting_opts(level)
    )


def _enter_green(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN)
    state.set(_KEY_LAST_MOTION_TIME, state.total)
    state.set(_KEY_MOTION_EMA, 0.0)
    state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0x00FF00})
    receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.green_light_music", {})
    state.set(_KEY_MUSIC_RECEIPT, receipt)


def _enter_level_up(state: GameState) -> None:
    _enter_phase(state, PHASE_LEVEL_UP)
    level = state.get(_KEY_LEVEL, 1) + 1
    state.set(_KEY_LEVEL, level)
    max_level = rlgl_config(state).max_level
    receipt = state.effect_controls.set_effect(
        Scope.AMBIENT, "basic.progress", {"progress": level / max_level}
    )
    state.set(_KEY_LEVEL_RECEIPT, receipt)
    state.effect_controls.add_effect(Scope.NON_AMBIENT, "scene.level_up", {})


def _enter_win(state: GameState) -> None:
    _enter_phase(state, PHASE_WIN)
    state.effect_controls.set_effect(Scope.ALL, "elements.lightning", {"level": 7})
    receipt = state.effect_controls.add_effect(Scope.ALL, "scene.win_sting", {})
    state.set(_KEY_WIN_STING_RECEIPT, receipt)


def _enter_game_over(state: GameState) -> None:
    _enter_phase(state, PHASE_GAME_OVER)
    state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
    state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})


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
    config = rlgl_config(state)
    beta = config.gravity_beta
    if state.has(_KEY_GRAVITY_X):
        gx = low_pass(state.get(_KEY_GRAVITY_X, accel.x), accel.x, beta)
        gy = low_pass(state.get(_KEY_GRAVITY_Y, accel.y), accel.y, beta)
        gz = low_pass(state.get(_KEY_GRAVITY_Z, accel.z), accel.z, beta)
    else:
        gx, gy, gz = accel.x, accel.y, accel.z
    state.set(_KEY_GRAVITY_X, gx)
    state.set(_KEY_GRAVITY_Y, gy)
    state.set(_KEY_GRAVITY_Z, gz)

    alpha = config.motion_smoothing
    linear = linear_magnitude(accel, gx, gy, gz)
    ema = low_pass(state.get(_KEY_MOTION_EMA, 0.0), linear, alpha)
    state.set(_KEY_MOTION_EMA, ema)
    return ema


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class RlglGameRule(GameRule):
    """Drives the Red Light Green Light eight-phase state machine.

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
        elif phase == PHASE_LEVEL_UP:
            self._check_level_up(state, phase_elapsed)
        elif phase == PHASE_WIN:
            self._check_win(state)
        elif phase == PHASE_GAME_OVER:
            self._check_game_over(state, phase_elapsed)

    def _check_ready(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            _start_game(state)

    def _check_red_warning(self, state: GameState, elapsed: float) -> None:
        level = state.get(_KEY_LEVEL, 1)
        if elapsed >= rlgl_config(state).warning_duration(level):
            _enter_red(state)

    def _check_red(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        elapsed: float,
    ) -> None:
        # Timer expiry is always checked before motion
        level = state.get(_KEY_LEVEL, 1)
        if elapsed >= rlgl_config(state).red_duration(level):
            _enter_green_warning(state)
            return

        if event.acceleration is not None:
            ema = _update_motion(state, event.acceleration)
            if ema > RED_MAX_MOTION_THRESHOLD:
                _enter_game_over(state)

    def _check_green_warning(self, state: GameState, elapsed: float) -> None:
        level = state.get(_KEY_LEVEL, 1)
        if elapsed >= rlgl_config(state).warning_duration(level):
            _enter_green(state)

    def _check_green(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        elapsed: float,
    ) -> None:
        # Timer expiry is always checked before motion
        config = rlgl_config(state)
        level = state.get(_KEY_LEVEL, 1)
        if elapsed >= config.green_duration(level):
            if level < config.max_level:
                _enter_level_up(state)
            else:
                _enter_win(state)
            return

        if event.acceleration is not None:
            ema = _update_motion(state, event.acceleration)
            if ema >= GREEN_MIN_MOTION_THRESHOLD:
                state.set(_KEY_LAST_MOTION_TIME, state.total)
            else:
                still_timeout = config.green_still_timeout
                last_motion = state.get(_KEY_LAST_MOTION_TIME, state.total)
                if state.total - last_motion >= still_timeout:
                    _enter_game_over(state)

    def _check_level_up(self, state: GameState, elapsed: float) -> None:
        if elapsed >= rlgl_config(state).level_up_duration:
            _enter_red_warning(state)

    def _check_win(self, state: GameState) -> None:
        receipt = state.get(_KEY_WIN_STING_RECEIPT, None)
        if receipt is not None and receipt.is_stopped():
            _enter_ready(state)

    def _check_game_over(self, state: GameState, elapsed: float) -> None:
        if elapsed >= rlgl_config(state).game_over_duration:
            _enter_ready(state)


RULE = RlglGameRule()
