"""Tag scene Ready phase rule.

On entry, plays the scene's "ready" effect across the whole device, layered
with the one-shot "ready_shots" audio sting announcing a live blaster. Any
button press transitions to Starting.
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_READY, PHASE_STARTING, tag_phase


class TagReadyRule(PhaseRule):
    """Drives the Ready phase: plays the ready effect and shot sting, waits for a button press."""

    def __init__(self) -> None:
        super().__init__(PHASE_READY, tag_phase)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "scene.ready", {})
        state.effect_controls.add_effect(Scope.ALL, "scene.ready_shots", {})

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if event.buttons.is_pressed("A") or event.buttons.is_pressed("B"):
            self.transition_to(state, PHASE_STARTING)


RULE = TagReadyRule()
