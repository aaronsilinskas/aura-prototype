from __future__ import annotations

from engine.input import InputEvents
from engine.network import NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import RADIO_FLASH_KEY, flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RADIO


class HwTestRadioRule(HwModeRule):
    """Drives the Radio mode: white idle entry effect, send + receive flash.

    On entry, shows a white solid on ``Scope.ALL``. Button A queues a
    simulated ``RadioReceived`` so the receive path can be exercised on a
    single board. Receiving a radio packet flashes ``Scope.Global.ALL`` with
    a white solid and records the receipt/timestamp so the shared
    ``HwModeRule`` flash-expiry can restore the idle effect.
    """

    def __init__(self) -> None:
        super().__init__(MODE_RADIO)
        self.on(NetworkEvents.RadioReceived, self._handle_radio_received)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "basic.solid", {"color": 0xFFFFFF})

    def on_button_a(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        state.queue_event(NetworkEvents.RadioReceived(HW_TEST_PAYLOAD, "local"))
        print("sending radio packet")

    def _handle_radio_received(self, event: NetworkEvents.RadioReceived, state: GameState) -> None:
        receipt = state.effect_controls.set_effect(
            Scope.Global.ALL, "basic.solid", {"color": 0xFFFFFF}
        )
        flash(state, RADIO_FLASH_KEY).restart(state.total, receipt)
        print("radio received " + str(event.data) + " from " + str(event.sender))


RULE = HwTestRadioRule()
