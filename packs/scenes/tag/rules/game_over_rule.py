"""Tag scene Game Over phase rule.

On entry, plays ``elements.fire`` across the whole device, adds the
scene-local game-over sting, and declares that the phase ends when the sting's
receipt stops, going back to Ready. The sting's ``EffectVerb.START`` audio clip
carries ``stops_effect=True``, so the end fires the moment the sound finishes.
There is no fixed duration; entering Ready replaces the looping fire with the
ready effect.
"""

from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_READY,
    tag_phase,
)


class TagGameOverRule(PhaseRule):
    """Drives the Game Over phase: fire + sting, then back to Ready."""

    def __init__(self) -> None:
        super().__init__(PHASE_GAME_OVER, tag_phase)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
        sting = state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})
        self.end_when_stopped(state, sting, PHASE_READY)


RULE = TagGameOverRule()
