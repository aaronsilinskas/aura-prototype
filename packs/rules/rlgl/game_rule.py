"""Red Light Green Light game rule — six-phase state machine driven by
accelerometer and buttons.

Phase flow::

    PHASE_READY → PHASE_RED_WARNING → PHASE_RED
                                          ↓ timer       ↓ motion (after grace)
                                   PHASE_GREEN_WARNING  PHASE_GAME_OVER
                                          ↓ timer              ↓ timer
                                     PHASE_GREEN          PHASE_READY
                                          ↓ timer  ↓ motion (after grace)
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

from engine.engine import GameRule, Version
from engine.input import ButtonData, InputEvents
from engine.state import GameState, Scope
from packs.rules.rlgl.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    RED_MAX_MOTION_THRESHOLD,
    motion_magnitude,
)

_VERSION: Final = Version(1, 0)

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
_KEY_GRACE_DURATION: Final = "rlgl_grace_duration"
_KEY_GAME_OVER_DURATION: Final = "rlgl_game_over_duration"

# ---------------------------------------------------------------------------
# Default durations (seconds)
# ---------------------------------------------------------------------------

_DEFAULT_WARNING_DURATION: Final = 2.0
_DEFAULT_RED_DURATION: Final = 5.0
_DEFAULT_GREEN_DURATION: Final = 5.0
_DEFAULT_GRACE_DURATION: Final = 1.0
_DEFAULT_GAME_OVER_DURATION: Final = 3.0

# ---------------------------------------------------------------------------
# Phase entry helpers
# ---------------------------------------------------------------------------


def _enter_ready(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_READY)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "elements.water", 3, {})


def _enter_red_warning(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_RED_WARNING)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", 10, {"color": 0xFF0000})


def _enter_red(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_RED)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", 10, {"color": 0xFF0000})


def _enter_green_warning(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_GREEN_WARNING)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", 10, {"color": 0x00FF00})


def _enter_green(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_GREEN)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "basic.solid", 10, {"color": 0x00FF00})


def _enter_game_over(state: GameState) -> None:
    state.set(_KEY_PHASE, PHASE_GAME_OVER)
    state.set(_KEY_PHASE_START, state.total)
    state.effect_controls.set_effect(Scope.ALL, "elements.fire", 10, {})


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class RlglGameRule(GameRule):
    """Drives the Red Light Green Light six-phase state machine.

    All mutable state is kept in ``GameState`` under ``rlgl_`` keys.  The rule
    itself is stateless beyond the registered event handler.
    """

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("rlgl.game", _VERSION)
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
        grace_duration = state.get(_KEY_GRACE_DURATION, _DEFAULT_GRACE_DURATION)

        # Timer expiry is always checked before motion
        if elapsed >= red_duration:
            _enter_green_warning(state)
            return

        if (
            event.acceleration is not None
            and elapsed >= grace_duration
            and motion_magnitude(event.acceleration) > RED_MAX_MOTION_THRESHOLD
        ):
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
        grace_duration = state.get(_KEY_GRACE_DURATION, _DEFAULT_GRACE_DURATION)

        # Timer expiry is always checked before motion
        if elapsed >= green_duration:
            _enter_red_warning(state)
            return

        if (
            event.acceleration is not None
            and elapsed >= grace_duration
            and motion_magnitude(event.acceleration) < GREEN_MIN_MOTION_THRESHOLD
        ):
            _enter_game_over(state)

    def _check_game_over(self, state: GameState, elapsed: float) -> None:
        duration = state.get(_KEY_GAME_OVER_DURATION, _DEFAULT_GAME_OVER_DURATION)
        if elapsed >= duration:
            _enter_ready(state)


RULE = RlglGameRule()
