from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_READY,
    tag_phase,
)


class TagGameOverRule(PhaseRule):
    """Plays fire and the game-over sting, then returns to Ready when the sting ends.

    The looping fire needs no ``on_exit``: entering Ready replaces it.
    """

    def __init__(self) -> None:
        super().__init__(PHASE_GAME_OVER, tag_phase)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
        sting = state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})
        self.end_when_stopped(state, sting, PHASE_READY)


RULE = TagGameOverRule()
