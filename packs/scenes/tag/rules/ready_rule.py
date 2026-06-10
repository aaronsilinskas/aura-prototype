"""Tag scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device. Any
button press transitions to Starting.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    KEY_ENTERED,
    KEY_PHASE,
    PHASE_READY,
    PHASE_STARTING,
)


class TagReadyRule(GameRule):
    """Drives the Ready phase: plays the ready effect, waits for a button press."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        phase = state.get(KEY_PHASE, PHASE_READY)
        if phase != PHASE_READY:
            return

        if not state.get(KEY_ENTERED, False):
            state.set(KEY_PHASE, PHASE_READY)
            state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
            state.set(KEY_ENTERED, True)

        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            state.set(KEY_PHASE, PHASE_STARTING)
            state.set(KEY_ENTERED, False)


RULE = TagReadyRule()
