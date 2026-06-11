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
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
    RED_MAX_MOTION_THRESHOLD,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_motion import rlgl_motion
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import (
    is_phase_state_initialized,
    rlgl_phase_state,
)

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
# Phase entry helpers
# ---------------------------------------------------------------------------


def _enter_phase(state: GameState, phase: str) -> None:
    """Record the new phase and its start time, stop any music left running by
    the previous phase, and drop the gravity estimate.

    Every ``_enter_*`` helper begins here, so a looping music effect can never
    leak across a transition.  ``RlglPhaseState.enter`` makes the music stop a
    no-op when nothing is playing (e.g. entering Ready at game start).
    Resetting the gravity estimate forces :meth:`RlglMotion.update` to re-seed
    from the first sample of the next phase rather than carrying a stale
    orientation across the transition.
    """
    rlgl_phase_state(state).enter(phase, state.total)
    rlgl_motion(state).reset_gravity()


def _enter_ready(state: GameState) -> None:
    _enter_phase(state, PHASE_READY)
    state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
    rlgl_phase_state(state).level_receipt = None


def _start_game(state: GameState) -> None:
    """Initialise a new game at level 1 and enter the Red Warning phase.

    Sets the Game Level to 1, starts the ``Scope.AMBIENT`` progress bar at
    ``1 / max_level`` (denominator from ``rlgl_max_level``, default 10), stores
    the receipt as ``level_receipt``, then hands off to
    ``_enter_red_warning``.  The level receipt persists across all mid-game
    phase transitions and is only cleared when ``_enter_ready`` is called.
    """
    phase_state = rlgl_phase_state(state)
    phase_state.level = 1
    max_level = rlgl_config(state).max_level
    receipt = state.effect_controls.set_effect(
        Scope.AMBIENT, "basic.progress", {"progress": 1 / max_level}
    )
    phase_state.level_receipt = receipt
    _enter_red_warning(state)


def _enter_red_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_RED_WARNING)
    level = rlgl_phase_state(state).level
    state.effect_controls.set_effect(
        Scope.NON_AMBIENT, "scene.warning_sting", rlgl_config(state).warning_sting_opts(level)
    )


def _enter_red(state: GameState) -> None:
    _enter_phase(state, PHASE_RED)
    rlgl_motion(state).ema = 0.0
    state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0xFF0000})
    receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.red_light_music", {})
    rlgl_phase_state(state).music_receipt = receipt


def _enter_green_warning(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN_WARNING)
    level = rlgl_phase_state(state).level
    state.effect_controls.set_effect(
        Scope.NON_AMBIENT, "scene.warning_sting", rlgl_config(state).warning_sting_opts(level)
    )


def _enter_green(state: GameState) -> None:
    _enter_phase(state, PHASE_GREEN)
    motion = rlgl_motion(state)
    motion.last_motion_time = state.total
    motion.ema = 0.0
    state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0x00FF00})
    receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.green_light_music", {})
    rlgl_phase_state(state).music_receipt = receipt


def _enter_level_up(state: GameState) -> None:
    _enter_phase(state, PHASE_LEVEL_UP)
    phase_state = rlgl_phase_state(state)
    level = phase_state.level + 1
    phase_state.level = level
    max_level = rlgl_config(state).max_level
    receipt = state.effect_controls.set_effect(
        Scope.AMBIENT, "basic.progress", {"progress": level / max_level}
    )
    phase_state.level_receipt = receipt
    state.effect_controls.add_effect(Scope.NON_AMBIENT, "scene.level_up", {})


def _enter_win(state: GameState) -> None:
    _enter_phase(state, PHASE_WIN)
    state.effect_controls.set_effect(Scope.ALL, "elements.lightning", {"level": 7})
    receipt = state.effect_controls.add_effect(Scope.ALL, "scene.win_sting", {})
    rlgl_phase_state(state).win_sting_receipt = receipt


def _enter_game_over(state: GameState) -> None:
    _enter_phase(state, PHASE_GAME_OVER)
    state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
    state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class RlglGameRule(GameRule):
    """Drives the Red Light Green Light eight-phase state machine.

    All mutable state is kept in :class:`RlglPhaseState`, plus the gravity and
    motion tracking in :class:`RlglMotion`.  The rule itself is stateless
    beyond the registered event handler.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        first_tick = not is_phase_state_initialized(state)
        phase_state = rlgl_phase_state(state)
        if first_tick:
            _enter_ready(state)

        phase = phase_state.phase
        phase_elapsed = phase_state.elapsed(state.total)

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
        level = rlgl_phase_state(state).level
        if elapsed >= rlgl_config(state).warning_duration(level):
            _enter_red(state)

    def _check_red(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        elapsed: float,
    ) -> None:
        # Timer expiry is always checked before motion
        level = rlgl_phase_state(state).level
        if elapsed >= rlgl_config(state).red_duration(level):
            _enter_green_warning(state)
            return

        if event.acceleration is not None:
            config = rlgl_config(state)
            ema = rlgl_motion(state).update(
                event.acceleration, config.gravity_beta, config.motion_smoothing
            )
            if ema > RED_MAX_MOTION_THRESHOLD:
                _enter_game_over(state)

    def _check_green_warning(self, state: GameState, elapsed: float) -> None:
        level = rlgl_phase_state(state).level
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
        level = rlgl_phase_state(state).level
        if elapsed >= config.green_duration(level):
            if level < config.max_level:
                _enter_level_up(state)
            else:
                _enter_win(state)
            return

        if event.acceleration is not None:
            motion = rlgl_motion(state)
            ema = motion.update(event.acceleration, config.gravity_beta, config.motion_smoothing)
            if ema >= GREEN_MIN_MOTION_THRESHOLD:
                motion.last_motion_time = state.total
            else:
                still_timeout = config.green_still_timeout
                if state.total - motion.last_motion_time >= still_timeout:
                    _enter_game_over(state)

    def _check_level_up(self, state: GameState, elapsed: float) -> None:
        if elapsed >= rlgl_config(state).level_up_duration:
            _enter_red_warning(state)

    def _check_win(self, state: GameState) -> None:
        receipt = rlgl_phase_state(state).win_sting_receipt
        if receipt is not None and receipt.is_stopped():
            _enter_ready(state)

    def _check_game_over(self, state: GameState, elapsed: float) -> None:
        if elapsed >= rlgl_config(state).game_over_duration:
            _enter_ready(state)


RULE = RlglGameRule()
