"""Tag scene hit-handling rule.

Subscribes to ``NetworkEvents.IRReceived`` and turns matching tag packets into
hitpoint loss while ``tag_phase`` is ``playing``. Decodes every received
packet (decoding never fails), then applies the accuracy-rig gate order:

1. Phase guard — only acts during the Playing phase.
2. Identity gate — counts only packets matching ``tag_expected_team`` /
   ``tag_expected_player``; mismatches are logged and ignored.
3. Deafen gate — packets received before ``tag_deafen_until`` (the player's
   own freshly-fired echo, which carries the expected identity) are logged
   and suppressed.
4. Hit — subtracts the decoded ``damage`` from hitpoints and re-issues the
   ``Scope.PERSONAL`` ``basic.progress`` bar with the new fraction (clamped to
   ``[0, 1]`` by the layer).
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.network import NetworkEvents
from engine.state import GameState, Scope
from hardware.shared.tag_protocol import decode_tag_data
from packs.scenes.tag.rules.helpers.phases import (
    DEFAULT_DEAFEN_UNTIL,
    DEFAULT_EXPECTED_PLAYER,
    DEFAULT_EXPECTED_TEAM,
    DEFAULT_STARTING_HITPOINTS,
    KEY_DEAFEN_UNTIL,
    KEY_EXPECTED_PLAYER,
    KEY_EXPECTED_TEAM,
    KEY_HITPOINTS,
    KEY_PHASE,
    KEY_STARTING_HITPOINTS,
    PHASE_PLAYING,
)


class TagHitRule(GameRule):
    """Drives hit detection during the Playing phase from received IR packets."""

    def __init__(self) -> None:
        self.on(NetworkEvents.IRReceived, self._handle)

    def _handle(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        phase = state.get(KEY_PHASE, "ready")
        if phase != PHASE_PLAYING:
            return

        tag_data = decode_tag_data(event.data)

        expected_team = state.get(KEY_EXPECTED_TEAM, DEFAULT_EXPECTED_TEAM)
        expected_player = state.get(KEY_EXPECTED_PLAYER, DEFAULT_EXPECTED_PLAYER)
        if tag_data.team != expected_team or tag_data.player != expected_player:
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

        deafen_until = state.get(KEY_DEAFEN_UNTIL, DEFAULT_DEAFEN_UNTIL)
        if state.total < deafen_until:
            print(
                "[deafened team="
                + str(tag_data.team)
                + " player="
                + str(tag_data.player)
                + " margin="
                + str(event.error_margin)
                + "]"
            )
            return

        hitpoints = state.get(KEY_HITPOINTS, DEFAULT_STARTING_HITPOINTS)
        hitpoints -= tag_data.damage
        state.set(KEY_HITPOINTS, hitpoints)

        starting_hitpoints = state.get(KEY_STARTING_HITPOINTS, DEFAULT_STARTING_HITPOINTS)
        fraction = hitpoints / starting_hitpoints
        state.effect_controls.set_effect(Scope.PERSONAL, "basic.progress", {"progress": fraction})

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
