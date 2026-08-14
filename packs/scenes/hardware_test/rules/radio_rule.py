from __future__ import annotations

from engine.input import InputEvents
from engine.network import NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import radio_flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RADIO


class HwTestRadioRule(HwModeRule):
    """Drives the Radio mode: white idle entry effect, send + receive flash.

    On entry, shows a white solid on ``Scope.ALL``. Button A transmits
    ``HW_TEST_PAYLOAD`` via ``state.network_controls.send_radio`` — a real
    over-the-air packet, not a local simulation. Receiving a genuine radio
    packet flashes ``Scope.Global.ALL`` with a white solid and records the
    receipt/timestamp so the shared ``HwModeRule`` flash-expiry can restore
    the idle effect.
    """

    def __init__(self) -> None:
        super().__init__(MODE_RADIO)
        self.on(NetworkEvents.RadioReceived, self._handle_radio_received)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "basic.solid", {"color": 0xFFFFFF})

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        state.network_controls.send_radio(HW_TEST_PAYLOAD)
        print("sending radio packet")

    def _handle_radio_received(self, event: NetworkEvents.RadioReceived, state: GameState) -> None:
        receipt = state.effect_controls.set_effect(
            Scope.Global.ALL, "basic.solid", {"color": 0xFFFFFF}
        )
        radio_flash(state).restart(state.total, receipt)
        print("radio received " + str(event.data) + " from " + str(event.sender))


RULE = HwTestRadioRule()
