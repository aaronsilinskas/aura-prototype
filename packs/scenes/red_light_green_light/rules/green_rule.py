"""RLGL scene Green phase rule.

On entry, drops the gravity estimate (re-seeding it from the first sample of
this phase rather than carrying a stale orientation across the transition),
resets the motion EMA and still-timer, shows solid green on
``Scope.NON_AMBIENT``, and starts the looping green-light music on
``Scope.PERSONAL``. Motion above the green motion threshold resets the
still-timer; sustained stillness past ``green_still_timeout`` ends the game.
On timer expiry, advances to Level Up (level below max) or Win (level at
max). On exit, stops the music so it never leaks into the next phase.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    GREEN_MIN_MOTION_THRESHOLD,
)
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_GREEN,
    PHASE_LEVEL_UP,
    PHASE_WIN,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_motion import rlgl_motion
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_rule import RlglPhaseRule
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglGreenRule(RlglPhaseRule):
    """Drives the Green phase: solid green, music, and the stillness gate."""

    def __init__(self) -> None:
        super().__init__(PHASE_GREEN)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        motion = rlgl_motion(state)
        motion.reset_gravity()
        motion.last_motion_time = state.total
        motion.ema = 0.0
        state.effect_controls.set_effect(Scope.NON_AMBIENT, "basic.solid", {"color": 0x00FF00})
        receipt = state.effect_controls.add_effect(Scope.PERSONAL, "scene.green_light_music", {})
        rlgl_phase_state(state).music_receipt = receipt

    def on_exit(self, state: GameState) -> None:
        rlgl_phase_state(state).stop_music()

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        # Timer expiry is always checked before motion
        config = rlgl_config(state)
        level = rlgl_phase_state(state).level
        elapsed = rlgl_phase(state).elapsed(state.total)
        if elapsed >= config.green_duration(level):
            if level < config.max_level:
                self.transition_to(state, PHASE_LEVEL_UP)
            else:
                self.transition_to(state, PHASE_WIN)
            return

        if event.acceleration is not None:
            motion = rlgl_motion(state)
            ema = motion.update(event.acceleration, config.gravity_beta, config.motion_smoothing)
            if ema >= GREEN_MIN_MOTION_THRESHOLD:
                motion.last_motion_time = state.total
            else:
                still_timeout = config.green_still_timeout
                if state.total - motion.last_motion_time >= still_timeout:
                    self.transition_to(state, PHASE_GAME_OVER)


RULE = RlglGreenRule()
