"""RLGL scene Level Up phase rule.

On entry, increments the Game Level, updates the ``Scope.AMBIENT`` progress
bar to the new level's fraction (storing the new receipt as
``level_receipt``), and plays the level-up sting on ``Scope.NON_AMBIENT``.
Transitions back to Red Warning after ``rlgl_level_up_duration``.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.red_light_green_light.rules.helpers.phases import (
    PHASE_LEVEL_UP,
    PHASE_RED_WARNING,
    rlgl_phase,
)
from packs.scenes.red_light_green_light.rules.helpers.rlgl_config import rlgl_config
from packs.scenes.red_light_green_light.rules.helpers.rlgl_phase_state import rlgl_phase_state


class RlglLevelUpRule(PhaseRule):
    """Drives the Level Up phase: increments Game Level, then back to Red Warning."""

    def __init__(self) -> None:
        super().__init__(PHASE_LEVEL_UP, rlgl_phase)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        phase_state = rlgl_phase_state(state)
        level = phase_state.level + 1
        phase_state.level = level
        max_level = rlgl_config(state).max_level
        receipt = state.effect_controls.set_effect(
            Scope.AMBIENT, "basic.progress", {"progress": level / max_level}
        )
        phase_state.level_receipt = receipt
        state.effect_controls.add_effect(Scope.NON_AMBIENT, "scene.level_up", {})

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if rlgl_phase(state).elapsed(state.total) >= rlgl_config(state).level_up_duration:
            self.transition_to(state, PHASE_RED_WARNING)


RULE = RlglLevelUpRule()
