from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule
from engine.input import InputEvents
from engine.network import LINE, NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import IR_FLASH_KEY, RADIO_FLASH_KEY, flash
from packs.scenes.hardware_test.rules.helpers.mode import MODE_IR, MODE_RADIO, current_mode

HW_TEST_PAYLOAD: Final = b"hw_test"


class HwTestNetworkRule(GameRule):
    """Owns Button A send + receive logging for the IR and radio modes.

    Button A (mode 2): transmits ``HW_TEST_PAYLOAD`` via the LINE emitter and
    fires the ``scene.sfx_test`` "sent" cue on ``Scope.PERSONAL``.

    Button A (mode 3): queues a simulated ``RadioReceived`` so the receive path
    can be exercised on a single board.

    IR receive (mode 2): flashes ``Scope.DIRECTIONAL`` with a white solid and
    records the receipt/timestamp so ``HwTestModeRule`` can expire the flash.

    Radio receive (mode 3): flashes ``Scope.Global.ALL`` with a white solid
    similarly.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle_button)
        self.on(NetworkEvents.IRReceived, self._handle_ir)
        self.on(NetworkEvents.RadioReceived, self._handle_radio)

    def _handle_button(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return
        mode = current_mode(state)
        if mode == MODE_IR:
            state.network_controls.send_ir(HW_TEST_PAYLOAD, LINE)
            state.effect_controls.set_effect(Scope.PERSONAL, "scene.sfx_test", {})
            print("sending IR packet")
        elif mode == MODE_RADIO:
            state.queue_event(NetworkEvents.RadioReceived(HW_TEST_PAYLOAD, "local"))
            print("sending radio packet")

    def _handle_ir(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        if current_mode(state) != MODE_IR:
            return
        receipt = state.effect_controls.set_effect(
            Scope.DIRECTIONAL, "basic.solid", {"color": 0xFFFFFF}
        )
        flash(state, IR_FLASH_KEY).restart(state.total, receipt)
        print(
            "ir received "
            + str(event.data)
            + " strength="
            + str(event.signal_strength)
            + " margin="
            + str(event.error_margin)
        )

    def _handle_radio(self, event: NetworkEvents.RadioReceived, state: GameState) -> None:
        if current_mode(state) != MODE_RADIO:
            return
        receipt = state.effect_controls.set_effect(
            Scope.Global.ALL, "basic.solid", {"color": 0xFFFFFF}
        )
        flash(state, RADIO_FLASH_KEY).restart(state.total, receipt)
        print("radio received " + str(event.data) + " from " + str(event.sender))


RULE = HwTestNetworkRule()
