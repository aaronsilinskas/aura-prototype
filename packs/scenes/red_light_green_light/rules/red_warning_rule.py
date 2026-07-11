"""RLGL scene Red Warning phase rule.

On entry, shows the warning sting (scaled to the current Game Level's pulse
duration) on ``Scope.NON_AMBIENT``. Transitions to Red once the warning
duration for the current level has elapsed.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_RED,
    PHASE_RED_WARNING,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglRedWarningRule(PhaseRule):
    """Drives the Red Warning phase: warning sting, then into Red."""

    def __init__(self) -> None:
        super().__init__(PHASE_RED_WARNING, rlgl_phase)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        level = rlgl_phase_state(state).level
        state.effect_controls.set_effect(
            Scope.NON_AMBIENT, "scene.warning_sting", rlgl_config(state).warning_sting_opts(level)
        )

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        level = rlgl_phase_state(state).level
        if rlgl_phase(state).elapsed(state.total) >= rlgl_config(state).warning_duration(level):
            self.transition_to(state, PHASE_RED)


RULE = RlglRedWarningRule()
