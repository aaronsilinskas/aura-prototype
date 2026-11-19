from __future__ import annotations

from engine.input import InputEvents
from engine.network import LINE
from engine.phase import InPhaseRule
from engine.state import GameState, Scope
from packs.scenes.tag.rules.helpers.phases import PHASE_PLAYING, tag_phase
from packs.scenes.tag.rules.helpers.tag_config import TagConfig, tag_config
from packs.scenes.tag.rules.helpers.tag_state import TagState, tag_state
from packs.scenes.tag.rules.playing_rule import AMMO_COLOR
from packs.scenes.tag.tag_data import TagData, encode_tag_data

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_SHOT_DAMAGE: Final = 1


class TagShootingRule(InPhaseRule):
    def __init__(self) -> None:
        super().__init__(PHASE_PLAYING, tag_phase)
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        tag = tag_state(state)
        config = tag_config(state)

        reload_started_at = tag.shot.reload_started_at
        if reload_started_at is not None:
            self._handle_reload(event, state, tag, config, reload_started_at)
            return

        if event.buttons.is_pressed("A"):
            if tag.shot.ammo == 0:
                state.effect_controls.add_effect(Scope.DIRECTIONAL, "scene.dry_fire", {})
                tag.shot.reload_started_at = state.total
                tag.shot.reload_receipt = state.effect_controls.set_effect(
                    Scope.Global.BUFF, "scene.reload", {"duration": config.reload_duration}
                )
            elif self._can_fire(state, tag, config):
                self._fire_shot(state, tag, config)

    def _handle_reload(
        self,
        event: InputEvents.Sensors,
        state: GameState,
        tag: TagState,
        config: TagConfig,
        reload_started_at: float,
    ) -> None:
        reload_complete = state.total - reload_started_at >= config.reload_duration
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
        self._end_reload(tag)

    def _cancel_reload(self, state: GameState, tag: TagState) -> None:
        state.effect_controls.set_effect(Scope.Global.BUFF, "scene.ammo_empty", {})
        self._end_reload(tag)

    def _end_reload(self, tag: TagState) -> None:
        tag.shot.reload_started_at = None
        reload_receipt = tag.shot.reload_receipt
        assert reload_receipt is not None  # set together with reload_started_at
        reload_receipt.stop()
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
