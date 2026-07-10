"""Tag scene hit-handling rule.

A non-owning :class:`InPhaseRule` reactor on the Playing phase: it subscribes
to ``NetworkEvents.IRReceived`` and turns matching tag packets into hitpoint
loss while the shared phase machine is in Playing, but it does not own the
phase's lifecycle. Decodes every received packet (decoding never fails), then
applies the accuracy-rig gate order:

1. Phase guard — the ``InPhaseRule`` only fires during the Playing phase.
2. Identity gate — counts only packets matching the configured expected
   team/player; mismatches are logged and ignored.
3. Hit — subtracts the decoded ``damage`` from hitpoints, re-issues the
   shared ``Scope.PERSONAL`` ``basic.progress`` bar (owned by the Playing rule)
   with the new fraction (clamped to ``[0, 1]`` by the layer), and plays the
   shared ``scene.hit`` effect on ``Scope.Global.MAIN``.

A genuine self-echo (the device's own freshly-fired packet looping back into
its own receiver) never reaches this rule — it is suppressed at the hardware
boundary by the IR transmit gate (see ``hardware.shared.ir_transport``), not
here. A matching incoming packet that does reach this rule always damages.
"""

from __future__ import annotations

from engine.network import NetworkEvents
from engine.phase import InPhaseRule
from engine.state import GameState, Scope
from hardware.shared.tag_protocol import decode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, tag_phase
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_state import tag_state


class TagHitRule(InPhaseRule):
    """Drives hit detection during the Playing phase from received IR packets."""

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING, tag_phase)
        self.on(NetworkEvents.IRReceived, self._handle)

    def _handle(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        tag = tag_state(state)
        config = tag_config(state)

        tag_data = decode_tag_data(event.data)

        if tag_data.team != config.expected_team or tag_data.player != config.expected_player:
            print(
                "[ignored team="
                + str(tag_data.team)
                + " player="
                + str(tag_data.player)
                + " margin="
                + str(event.error_margin)
                + "]"
            )
            return

        tag.hitpoints -= tag_data.damage

        fraction = tag.hitpoints / config.starting_hitpoints
        tag.hitpoints_receipt = state.effect_controls.set_effect(
            Scope.PERSONAL, "basic.progress", {"progress": fraction, "color": 0x00FF00}
        )

        state.effect_controls.set_effect(Scope.Global.MAIN, "scene.hit", {})

        print(
            "[hit team="
            + str(tag_data.team)
            + " player="
            + str(tag_data.player)
            + " damage="
            + str(tag_data.damage)
            + " signal_strength="
            + str(event.signal_strength)
            + " error_margin="
            + str(event.error_margin)
            + "]"
        )


RULE = TagHitRule()
