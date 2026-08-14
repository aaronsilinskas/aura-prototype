"""Tag scene Game Over phase rule.

On entry, plays ``elements.fire`` across the whole device and adds the
scene-local game-over sting, storing its ``EffectReceipt`` on ``TagState``.
Stays in ``game_over`` until the sting's receipt reports stopped (the sting's
"start" audio clip carries ``stops_effect=True``, so this fires the moment
the sound finishes), then transitions back to Ready. There is no fixed
duration — entering Ready replaces the looping fire with the ready effect.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_READY,
    tag_phase,
)
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagGameOverRule(PhaseRule):
    """Drives the Game Over phase: fire + sting, then back to Ready."""

    def __init__(self) -> None:
        super().__init__(PHASE_GAME_OVER, tag_phase)
        self.on(InputEvents.Sensors, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
        tag_state(state).game_over_receipt = state.effect_controls.add_effect(
            Scope.ALL, "scene.game_over_sting", {}
        )

    def on_exit(self, state: GameState) -> None:
        tag_state(state).game_over_receipt = None

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        receipt = tag_state(state).game_over_receipt
        if receipt is not None and receipt.is_stopped():
            self.transition_to(state, PHASE_READY)


RULE = TagGameOverRule()
