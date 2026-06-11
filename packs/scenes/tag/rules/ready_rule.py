"""Tag scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device. Any
button press transitions to Starting.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, PHASE_STARTING
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagReadyRule(GameRule):
    """Drives the Ready phase: plays the ready effect, waits for a button press."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)
        if tag.phase != PHASE_READY:
            return

        if tag.just_entered:
            state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
            tag.mark_entered()

        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            tag.enter(PHASE_STARTING)


RULE = TagReadyRule()
