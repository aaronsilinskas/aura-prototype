"""Tag scene Playing phase rule.

On entry, sets hitpoints to the configured starting value and shows a full
``basic.progress`` bar on ``Scope.PERSONAL``, storing its ``EffectReceipt`` (the
shared progress receipt this rule owns and the hit reactor re-issues). Button-A
shot firing and its felt feedback are owned by :class:`TagShootingRule`; this
rule retains only the phase lifecycle: hitpoints, the progress bar, and the
game-over transition when hitpoints reach zero or below (stopping the progress
bar on the way out).
"""

from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_GAME_OVER, PHASE_PLAYING
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_phase_rule import TagPhaseRule
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagPlayingRule(TagPhaseRule):
    """Drives the Playing phase: hitpoints, progress bar, and game-over transition."""

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        tag = tag_state(state)
        tag.hitpoints = tag_config(state).starting_hitpoints
        tag.progress_receipt = state.effect_controls.set_effect(
            Scope.PERSONAL, "basic.progress", {"progress": 1.0}
        )

    def on_exit(self, state: GameState) -> None:
        tag = tag_state(state)
        if tag.progress_receipt is not None:
            tag.progress_receipt.stop()
            tag.progress_receipt = None

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)

        if tag.hitpoints <= 0:
            self.transition_to(state, PHASE_GAME_OVER)


RULE = TagPlayingRule()
