"""Tag scene Playing phase rule.

On entry, sets hitpoints to the configured starting value and shows a full
``basic.progress`` bar on ``Scope.PERSONAL``, storing its ``EffectReceipt``.
Button A fires a shot: encodes the player's own ``TagData`` identity, sends
it on the LINE IR emitter, logs the send, and starts the self-deafen window
so the player's own shot is not immediately registered as a hit. When
hitpoints reach zero or below, transitions to the ``game_over`` phase.
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
from packs.scenes.tag.rules.helpers.phases import PHASE_GAME_OVER, PHASE_PLAYING
from packs.scenes.tag.rules.helpers.tag_config import TagConfig, tag_config
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state

_SHOT_DAMAGE: Final = 1


class TagPlayingRule(GameRule):
    """Drives the Playing phase: hitpoints, progress bar, and shot firing."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)
        if tag.phase != PHASE_PLAYING:
            return

        config = tag_config(state)

        if tag.just_entered:
            tag.hitpoints = config.starting_hitpoints
            tag.progress_receipt = state.effect_controls.set_effect(
                Scope.PERSONAL, "basic.progress", {"progress": 1.0}
            )
            tag.mark_entered()

        if event.buttons.is_pressed("A"):
            self._fire_shot(state, tag, config)

        if tag.hitpoints <= 0:
            tag.enter(PHASE_GAME_OVER)

    def _fire_shot(self, state: GameState, tag: TagState, config: TagConfig) -> None:
        payload = encode_tag_data(
            TagData(config.expected_team, config.expected_player, _SHOT_DAMAGE)
        )
        state.network_controls.send_ir(payload, LINE)
        print("sending IR packet")

        tag.deafen_until = state.total + config.deafen_window


RULE = TagPlayingRule()
