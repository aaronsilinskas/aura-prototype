from __future__ import annotations

from engine.network import NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import radio_flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD, RECEIVE_FLASH_COLOR
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RADIO

TYPE_CHECKING = False

if TYPE_CHECKING:
    from engine.input import InputEvents


class HwTestRadioRule(HwModeRule):
    def __init__(self) -> None:
        super().__init__(MODE_RADIO, "radio")
        self.on(NetworkEvents.RadioReceived, self._handle_radio_received)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(
            Scope.ALL, "basic.solid", {"color": self.idle_color(state)}
        )

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        state.network_controls.send_radio(HW_TEST_PAYLOAD)
        print("sending radio packet")

    def _handle_radio_received(self, event: NetworkEvents.RadioReceived, state: GameState) -> None:
        receipt = state.effect_controls.set_effect(
            Scope.Global.ALL, "basic.solid", {"color": RECEIVE_FLASH_COLOR}
        )
        radio_flash(state).restart(state.total, receipt)
        print("radio received " + str(event.data) + " from " + str(event.sender))


RULE = HwTestRadioRule()
