"""Tag scene Game Over phase rule.

On entry, plays ``elements.fire`` across the whole device and adds the
scene-local game-over sting, storing its ``EffectReceipt``. Stays in
``game_over`` until the sting's receipt reports stopped (the sting's "start"
audio clip carries ``stops_effect=True``, so this fires the moment the sound
finishes), then transitions back to Ready. There is no fixed duration —
entering Ready replaces the looping fire with the ready effect.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    KEY_ENTERED,
    KEY_GAME_OVER_RECEIPT,
    KEY_PHASE,
    PHASE_GAME_OVER,
    PHASE_READY,
)


class TagGameOverRule(GameRule):
    """Drives the Game Over phase: fire + sting, then back to Ready."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        phase = state.get(KEY_PHASE, "ready")
        if phase != PHASE_GAME_OVER:
            return

        if not state.get(KEY_ENTERED, False):
            state.effect_controls.set_effect(Scope.ALL, "elements.fire", {})
            receipt = state.effect_controls.add_effect(Scope.ALL, "scene.game_over_sting", {})
            state.set(KEY_GAME_OVER_RECEIPT, receipt)
            state.set(KEY_ENTERED, True)

        receipt = state.get(KEY_GAME_OVER_RECEIPT, None)
        if receipt is not None and receipt.is_stopped():
            state.set(KEY_PHASE, PHASE_READY)
            state.set(KEY_ENTERED, False)
            state.delete(KEY_GAME_OVER_RECEIPT)


RULE = TagGameOverRule()
