from __future__ import annotations

from engine.input import InputEvents
from engine.network import LINE, NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import ir_flash
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.rules.helpers.phases import MODE_IR


class HwTestIrRule(HwModeRule):
    """Drives the IR mode: white idle entry effect, send + receive flash.

    On entry, shows a white solid on ``Scope.ALL``. Button A transmits
    ``HW_TEST_PAYLOAD`` via the LINE IR emitter and fires the
    ``scene.sfx_test`` "sent" cue on ``Scope.PERSONAL``. Receiving an IR
    packet flashes ``Scope.DIRECTIONAL`` with a white solid and records the
    receipt/timestamp so the shared ``HwModeRule`` flash-expiry can restore
    the idle effect.
    """

    def __init__(self) -> None:
        super().__init__(MODE_IR)
        self.on(NetworkEvents.IRReceived, self._handle_ir_received)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.ALL, "basic.solid", {"color": 0xFFFFFF})

    def on_input_event(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        state.network_controls.send_ir(HW_TEST_PAYLOAD, LINE)
        state.effect_controls.set_effect(Scope.PERSONAL, "scene.sfx_test", {})
        print("sending IR packet")

    def _handle_ir_received(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        receipt = state.effect_controls.set_effect(
            Scope.DIRECTIONAL, "basic.solid", {"color": 0xFFFFFF}
        )
        ir_flash(state).restart(state.total, receipt)
        print(
            "ir received "
            + str(event.data)
            + " strength="
            + str(event.signal_strength)
            + " margin="
            + str(event.error_margin)
        )


RULE = HwTestIrRule()
