"""Tag scene Playing phase rule.

On entry, sets hitpoints to the configured starting value and shows a full
``basic.progress`` bar on ``Scope.PERSONAL``. Button A fires a shot: encodes
the player's own ``TagData`` identity, sends it on the LINE IR emitter, logs
the send, and starts the self-deafen window so the player's own shot is not
immediately registered as a hit.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.engine import GameRule
from engine.input import InputEvents
from engine.network import LINE
from engine.state import GameState, Scope
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import (
    DEFAULT_DEAFEN_WINDOW,
    DEFAULT_EXPECTED_PLAYER,
    DEFAULT_EXPECTED_TEAM,
    DEFAULT_STARTING_HITPOINTS,
    KEY_DEAFEN_UNTIL,
    KEY_DEAFEN_WINDOW,
    KEY_ENTERED,
    KEY_EXPECTED_PLAYER,
    KEY_EXPECTED_TEAM,
    KEY_HITPOINTS,
    KEY_PHASE,
    KEY_STARTING_HITPOINTS,
    PHASE_PLAYING,
)

_SHOT_DAMAGE: Final = 1


class TagPlayingRule(GameRule):
    """Drives the Playing phase: hitpoints, progress bar, and shot firing."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        phase = state.get(KEY_PHASE, "ready")
        if phase != PHASE_PLAYING:
            return

        if not state.get(KEY_ENTERED, False):
            hitpoints = state.get(KEY_STARTING_HITPOINTS, DEFAULT_STARTING_HITPOINTS)
            state.set(KEY_HITPOINTS, hitpoints)
            state.effect_controls.set_effect(Scope.PERSONAL, "basic.progress", {"progress": 1.0})
            state.set(KEY_ENTERED, True)

        if event.buttons.is_pressed("A"):
            self._fire_shot(state)

    def _fire_shot(self, state: GameState) -> None:
        team = state.get(KEY_EXPECTED_TEAM, DEFAULT_EXPECTED_TEAM)
        player = state.get(KEY_EXPECTED_PLAYER, DEFAULT_EXPECTED_PLAYER)
        payload = encode_tag_data(TagData(team, player, _SHOT_DAMAGE))
        state.network_controls.send_ir(payload, LINE)
        print("sending IR packet")

        deafen_window = state.get(KEY_DEAFEN_WINDOW, DEFAULT_DEAFEN_WINDOW)
        state.set(KEY_DEAFEN_UNTIL, state.total + deafen_window)


RULE = TagPlayingRule()
