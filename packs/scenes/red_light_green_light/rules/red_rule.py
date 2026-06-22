"""RLGL scene Red phase rule.

On entry, drops the gravity estimate (re-seeding it from the first sample of
this phase rather than carrying a stale orientation across the transition),
resets the motion EMA, shows solid red on ``Scope.NON_AMBIENT``, and starts
the looping red-light music on ``Scope.PERSONAL``. Any motion above the red
motion threshold ends the game; otherwise the phase times out into Green
Warning. On exit, stops the music so it never leaks into the next phase.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    RED_MAX_MOTION_THRESHOLD,
)
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_GREEN_WARNING,
    PHASE_READY,
    PHASE_RED,
    RLGL_MACHINE_KEY,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_motion import rlgl_motion
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglRedRule(PhaseRule):
    """Drives the Red phase: solid red, music, and the motion gate."""

    def __init__(self) -> None:
        super().__init__(PHASE_RED, RLGL_MACHINE_KEY, PHASE_READY)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        motion = rlgl_motion(state)
        motion.reset_gravity()
        motion.ema = 0.0
        state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0xFF0000})
        receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.red_light_music", {})
        rlgl_phase_state(state).music_receipt = receipt

    def on_exit(self, state: GameState) -> None:
        rlgl_phase_state(state).stop_music()

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        # Timer expiry is always checked before motion
        level = rlgl_phase_state(state).level
        elapsed = rlgl_phase(state).elapsed(state.total)
        if elapsed >= rlgl_config(state).red_duration(level):
            self.transition_to(state, PHASE_GREEN_WARNING)
            return

        if event.acceleration is not None:
            config = rlgl_config(state)
            ema = rlgl_motion(state).update(
                event.acceleration, config.gravity_beta, config.motion_smoothing
            )
            if ema > RED_MAX_MOTION_THRESHOLD:
                self.transition_to(state, PHASE_GAME_OVER)


RULE = RlglRedRule()
