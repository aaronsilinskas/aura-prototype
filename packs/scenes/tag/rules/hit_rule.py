from __future__ import annotations

from engine.network import NetworkEvents
from engine.phase import InPhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, tag_phase
from packs.scenes.tag.rules.helpers.tag_config import tag_config
from packs.scenes.tag.rules.helpers.tag_state import tag_state
from packs.scenes.tag.tag_data import decode_tag_data


class TagHitRule(InPhaseRule):
    """Turns matching IR tag packets into hitpoint loss during Playing.

    A genuine self-echo (the device's own packet looping back into its
    receiver) never reaches this rule: the IR transmit gate in
    ``hardware.shared.ir_transport`` suppresses it, so every matching packet
    that arrives here damages.
    """

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
