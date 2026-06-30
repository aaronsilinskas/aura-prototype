"""Tag scene Playing phase rule.

On entry, sets hitpoints to the configured starting value and shows a full
``basic.progress`` bar on ``Scope.PERSONAL``, storing its ``EffectReceipt`` (the
shared progress receipt this rule owns and the hit reactor re-issues). It also
issues the full amber ammo bar on ``Scope.Global.BUFF`` and layers the one-shot
``scene.go`` cue on ``Scope.PERSONAL`` via ``add_effect`` (sound + strong buzz
marking the instant Playing begins). Button-A shot firing and its felt
feedback are owned by :class:`TagShootingRule`; this rule retains only the
phase lifecycle: hitpoints, the progress bar, the ammo bar, the GO cue, and
the game-over transition when hitpoints reach zero or below.

``Scope.Global.BUFF`` is a single mutually-exclusive "what's currently shown
for ammo" slot: the amber bar, ``scene.ammo_empty``, and ``scene.reload`` all
swap each other out via ``set_effect``. On exit, the whole slot is torn down
via ``stop_effect(Scope.Global.BUFF)`` rather than a stored receipt, since any
of those effects (or none) may be occupying it at the time.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.input import InputEvents
from engine.phase import PhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import (
    PHASE_GAME_OVER,
    PHASE_PLAYING,
    PHASE_READY,
    TAG_MACHINE_KEY,
)
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_state import tag_state

AMMO_COLOR: Final = 0xFFBF00


class TagPlayingRule(PhaseRule):
    """Drives the Playing phase: hitpoints, ammo bar, and game-over transition."""

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING, TAG_MACHINE_KEY, PHASE_READY)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def on_enter(self, state: GameState) -> None:
        tag = tag_state(state)
        tag.hitpoints = tag_config(state).starting_hitpoints
        tag.hitpoints_receipt = state.effect_controls.set_effect(
            Scope.PERSONAL, "basic.progress", {"progress": 1.0, "color": 0x00FF00}
        )

        tag.shot.ammo = tag_config(state).max_ammo
        tag.shot.reload_started_at = None
        tag.shot.reload_receipt = None
        state.effect_controls.set_effect(
            Scope.Global.BUFF, "basic.progress", {"progress": 1.0, "color": AMMO_COLOR}
        )

        state.effect_controls.add_effect(Scope.PERSONAL, "scene.go", {})

    def on_exit(self, state: GameState) -> None:
        tag = tag_state(state)
        if tag.hitpoints_receipt is not None:
            tag.hitpoints_receipt.stop()
            tag.hitpoints_receipt = None

        state.effect_controls.stop_effect(Scope.Global.BUFF)

        if tag.shot.reload_receipt is not None:
            tag.shot.reload_receipt.stop()
            tag.shot.reload_receipt = None
        tag.shot.reload_started_at = None

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)

        if tag.hitpoints <= 0:
            self.transition_to(state, PHASE_GAME_OVER)


RULE = TagPlayingRule()
