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
from engine.phase import InPhaseRule
from engine.state import GameState, Scope
from hardware.shared.tag_protocol import TagData, encode_tag_data
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, PHASE_READY, TAG_MACHINE_KEY
from packs.scenes.tag.rules.helpers.tag_config import TagConfig, tag_config
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state
from packs.scenes.tag.rules.playing_rule import AMMO_COLOR

_SHOT_DAMAGE: Final = 1


class TagShootingRule(InPhaseRule):
    """Drives Button-A shot firing and felt feedback during the Playing phase."""

    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING, TAG_MACHINE_KEY, PHASE_READY)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        tag = tag_state(state)
        config = tag_config(state)

        if tag.shot.reload_started_at is not None:
            self._handle_reload(event, state, tag, config)
            return

        if event.buttons.is_pressed("A"):
            if tag.shot.ammo == 0:
                tag.shot.reload_started_at = state.total
                tag.shot.reload_receipt = state.effect_controls.set_effect(
                    Scope.Global.BUFF, "scene.reload", {"duration": config.reload_duration}
                )
            elif self._can_fire(state, tag, config):
                self._fire_shot(state, tag, config)

    def _handle_reload(
        self,
        event: InputEvents.ButtonAndAcceleration,
        state: GameState,
        tag: TagState,
        config: TagConfig,
    ) -> None:
        reload_complete = state.total - tag.shot.reload_started_at >= config.reload_duration
        if reload_complete:
            self._complete_reload(state, tag, config)
        elif event.buttons.is_down("A"):
            return
        else:
            self._cancel_reload(state, tag)

    def _complete_reload(self, state: GameState, tag: TagState, config: TagConfig) -> None:
        tag.shot.ammo = config.max_ammo
        state.effect_controls.set_effect(
            Scope.Global.BUFF, "basic.progress", {"progress": 1.0, "color": AMMO_COLOR}
        )
        state.effect_controls.add_effect(Scope.Global.BUFF, "scene.reload_complete", {})
        tag.shot.reload_started_at = None
        tag.shot.reload_receipt.stop()
        tag.shot.reload_receipt = None

    def _cancel_reload(self, state: GameState, tag: TagState) -> None:
        state.effect_controls.set_effect(Scope.Global.BUFF, "scene.ammo_empty", {})
        tag.shot.reload_started_at = None
        tag.shot.reload_receipt.stop()
        tag.shot.reload_receipt = None

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
        if tag.shot.ammo > 0:
            state.effect_controls.set_effect(
                Scope.Global.BUFF,
                "basic.progress",
                {"progress": tag.shot.ammo / config.max_ammo, "color": AMMO_COLOR},
            )
        else:
            state.effect_controls.set_effect(Scope.Global.BUFF, "scene.ammo_empty", {})


RULE = TagShootingRule()
