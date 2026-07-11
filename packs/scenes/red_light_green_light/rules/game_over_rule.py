"""RLGL scene Game Over phase rule.

On entry, plays ``elements.fire`` and adds the game-over sting, both on
``Scope.ALL``. Transitions back to Ready after ``rlgl_game_over_duration``.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_READY,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config


class RlglGameOverRule(PhaseRule):
    """Drives the Game Over phase: fire + sting, then back to Ready."""

    def __init__(self) -> None:
        super().__init__(PHASE_GAME_OVER, rlgl_phase)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
        state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if rlgl_phase(state).elapsed(state.total) >= rlgl_config(state).game_over_duration:
            self.transition_to(state, PHASE_READY)


RULE = RlglGameOverRule()
