from __future__ import annotations

from engine.engine import GameRule
from engine.network import NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.hw_test.rules.helpers.mode import MODE_IR, MODE_RADIO, current_mode


class HwTestNetworkRule(GameRule):
    """Fires a timed flash effect on IR and radio receive events.

    IR receive (mode 2): flashes ``Scope.DIRECTIONAL`` with a white solid and records
    the receipt/timestamp so ``HwTestModeRule`` can expire the flash.

    Radio receive (mode 3): flashes ``Scope.Global.ALL`` with a white solid similarly.
    """

    def __init__(self) -> None:
        self.on(NetworkEvents.IRReceived, self._handle_ir)
        self.on(NetworkEvents.RadioReceived, self._handle_radio)

    def _handle_ir(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        if current_mode(state) != MODE_IR:
            return
        receipt = state.effect_controls.set_effect(
            Scope.DIRECTIONAL, "basic.solid", {"color": 0xFFFFFF}
        )
        state.set("ir_flash_receipt", receipt)
        state.set("ir_flash_start", state.total)

    def _handle_radio(self, event: NetworkEvents.RadioReceived, state: GameState) -> None:
        if current_mode(state) != MODE_RADIO:
            return
        receipt = state.effect_controls.set_effect(
            Scope.Global.ALL, "basic.solid", {"color": 0xFFFFFF}
        )
        state.set("radio_flash_receipt", receipt)
        state.set("radio_flash_start", state.total)


RULE = HwTestNetworkRule()
