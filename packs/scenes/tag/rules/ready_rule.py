"""Tag scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device. Any
button press transitions to Starting.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, PHASE_STARTING
from packs.scenes.tag.rules.helpers.tag_phase_rule import TagPhaseRule


class TagReadyRule(TagPhaseRule):
    """Drives the Ready phase: plays the ready effect, waits for a button press."""

    def __init__(self) -> None:
        super().__init__(PHASE_READY)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self.transition_to(state, PHASE_STARTING)


RULE = TagReadyRule()
