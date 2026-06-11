"""Tag scene Game Over phase rule.

On entry, plays ``elements.fire`` across the whole device and adds the
scene-local game-over sting, storing its ``EffectReceipt`` on ``TagState``.
Stays in ``game_over`` until the sting's receipt reports stopped (the sting's
"start" audio clip carries ``stops_effect=True``, so this fires the moment
the sound finishes), then transitions back to Ready. There is no fixed
duration — entering Ready replaces the looping fire with the ready effect.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_GAME_OVER, PHASE_READY
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagGameOverRule(GameRule):
    """Drives the Game Over phase: fire + sting, then back to Ready."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)
        if tag.phase != PHASE_GAME_OVER:
            return

        if tag.take_just_entered():
            state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
            tag.game_over_receipt = state.effect_controls.add_effect(
                Scope.ALL, "scene.game_over_sting", {}
            )

        receipt = tag.game_over_receipt
        if receipt is not None and receipt.is_stopped():
            tag.enter(PHASE_READY)
            tag.game_over_receipt = None


RULE = TagGameOverRule()
