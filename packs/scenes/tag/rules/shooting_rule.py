"""Tag scene Playing-phase shooting rule.

An :class:`InPhaseRule` active during the Playing phase that owns the
Button-A fire path. On a fresh Button-A press, it encodes the player's own
``TagData`` identity, sends it on the LINE IR emitter, logs the send, starts
the self-deafen window so the player's own shot is not immediately registered
as a hit, and plays the scene-local ``scene.fire_shot`` effect on
``Scope.DIRECTIONAL`` for felt feedback.

Phase lifecycle (hitpoints, the ``PERSONAL`` hitpoint bar, and the game-over
transition) remains owned by :class:`TagPlayingRule`.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # typing not available on all embedded runtimes

from engine.input import InputEvents
from engine.network import LINE
from engine.state import GameState, Scope
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING
from packs.scenes.tag.rules.helpers.tag_config import TagConfig, tag_config
from packs.scenes.tag.rules.helpers.tag_phase_rule import TagInPhaseRule
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state

_SHOT_DAMAGE: Final = 1


class TagShootingRule(TagInPhaseRule):
    """Drives Button-A shot firing and felt feedback during the Playing phase."""

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if event.buttons.is_pressed("A"):
            tag = tag_state(state)
            config = tag_config(state)
            if self._can_fire(state, tag, config):
                self._fire_shot(state, tag, config)

    def _can_fire(self, state: GameState, tag: TagState, config: TagConfig) -> bool:
        if tag.shot.ammo <= 0:
            return False
        return state.total - tag.shot.last_shot_at >= config.shot_cooldown

    def _fire_shot(self, state: GameState, tag: TagState, config: TagConfig) -> None:
        payload = encode_tag_data(
            TagData(config.expected_team, config.expected_player, _SHOT_DAMAGE)
        )
        state.network_controls.send_ir(payload, LINE)
        print("sending IR packet")

        tag.deafen_until = state.total + config.deafen_window

        tag.shot.ammo -= 1
        tag.shot.last_shot_at = state.total

        state.effect_controls.set_effect(Scope.DIRECTIONAL, "scene.fire_shot", {})
        state.effect_controls.set_effect(
            Scope.Global.BUFF, "basic.progress", {"progress": tag.shot.ammo / config.max_ammo}
        )


RULE = TagShootingRule()
