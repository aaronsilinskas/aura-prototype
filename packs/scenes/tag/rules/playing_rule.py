from __future__ import annotations

from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_PLAYING,
    tag_phase,
)
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_state import tag_state

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

AMMO_COLOR: Final = 0xFFBF00


class TagPlayingRule(PhaseRule):
    """Owns the Playing phase lifecycle: hitpoints, the hitpoint and ammo bars, and the GO cue.

    ``Global.BUFF`` is torn down with ``stop_effect`` rather than a stored
    receipt, since any of the ammo effects, or none, may hold it at exit.
    """

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING, tag_phase)

    def on_enter(self, state: GameState) -> None:
        tag = tag_state(state)
        tag.hitpoints = tag_config(state).starting_hitpoints
        tag.hitpoints_receipt = state.effect_controls.set_effect(
            Scope.PERSONAL, "basic.progress", {"progress": 1.0, "color": 0x00FF00}
        )

        tag.shot.ammo = tag_config(state).max_ammo
        tag.shot.reload = None
        state.effect_controls.set_effect(
            Scope.Global.BUFF, "basic.progress", {"progress": 1.0, "color": AMMO_COLOR}
        )

        state.effect_controls.add_effect(Scope.PERSONAL, "scene.go", {})
        self.end_when(state, _out_of_hitpoints, PHASE_GAME_OVER)

    def on_exit(self, state: GameState) -> None:
        tag = tag_state(state)
        if tag.hitpoints_receipt is not None:
            tag.hitpoints_receipt.stop()
            tag.hitpoints_receipt = None

        state.effect_controls.stop_effect(Scope.Global.BUFF)

        if tag.shot.reload is not None:
            tag.shot.reload.receipt.stop()
            tag.shot.reload = None


def _out_of_hitpoints(state: GameState) -> bool:
    return tag_state(state).hitpoints <= 0


RULE = TagPlayingRule()
