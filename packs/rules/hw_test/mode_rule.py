from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule, Version
from engine.input import ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.state import EffectReceipt, GameState, Scope

_VERSION: Final = Version(1, 0)

HW_TEST_PAYLOAD: Final = b"hw_test"
FLASH_DURATION: Final = 0.5

# RGB mode idle effect table: (scope, name, options)
_RGB_IDLE: Final = (
    (Scope.PERSONAL, "elements.water", {}),
    (Scope.DIRECTIONAL, "elements.fire", {}),
    (Scope.Global.MAIN, "elements.lightning", {}),
    (Scope.Global.BUFF, "elements.earth", {}),
    (Scope.Global.DEBUFF, "elements.ice", {}),
)


def _enter_rgb(state: GameState) -> None:
    ec = state.effect_controls
    level = 1
    state.set("rgb_level", level)
    for scope, name, options in _RGB_IDLE:
        ec.set_effect(scope, name, level, options)


def _enter_imu(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.PERSONAL, "basic.solid", 1, {"color": 0xFF0000})
    ec.set_effect(Scope.DIRECTIONAL, "basic.solid", 1, {"color": 0x00FF00})
    ec.set_effect(Scope.Global.ALL, "basic.solid", 1, {"color": 0x0000FF})


def _enter_ir(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.ALL, "basic.solid", 3, {"color": 0xFFFFFF})


def _enter_radio(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.ALL, "basic.solid", 3, {"color": 0xFFFFFF})


_MODE_ENTRY: Final = (_enter_rgb, _enter_imu, _enter_ir, _enter_radio)
_NUM_MODES: Final = 4


class HwTestModeRule(GameRule):
    """Drives hw_test mode transitions and Button A/B behaviour."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("hw_test.mode", _VERSION)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        # First-tick init: initialise mode from initial_mode
        if "hw_mode" not in state:
            mode = state.pop("initial_mode", int)
            state.set("hw_mode", mode)
            _MODE_ENTRY[mode](state)

        self._check_flash_expiry(state)

        buttons = event.buttons.states
        if buttons.get("B") == ButtonData.PRESSED:
            self._advance_mode(state)
        elif buttons.get("A") == ButtonData.PRESSED:
            self._handle_button_a(state)

    def _advance_mode(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)
        # Clear all flash keys
        state.delete("ir_flash_receipt")
        state.delete("ir_flash_start")
        state.delete("radio_flash_receipt")
        state.delete("radio_flash_start")

        new_mode = (state.get("hw_mode", 0) + 1) % _NUM_MODES
        state.set("hw_mode", new_mode)
        _MODE_ENTRY[new_mode](state)

    def _handle_button_a(self, state: GameState) -> None:
        mode = state.get("hw_mode", 0)
        if mode == 0:
            new_level = (state.get("rgb_level", 1) % 10) + 1
            state.set("rgb_level", new_level)
            ec = state.effect_controls
            for scope, name, options in _RGB_IDLE:
                ec.set_effect(scope, name, new_level, options)
        elif mode == 1:
            pass  # IMU mode: no-op
        elif mode == 2:
            state.queue_event(NetworkEvents.IRReceived(HW_TEST_PAYLOAD))
        elif mode == 3:
            state.queue_event(NetworkEvents.RadioReceived(HW_TEST_PAYLOAD, "local"))

    def _check_flash_expiry(self, state: GameState) -> None:
        if (
            "ir_flash_start" in state
            and state.total - state.get("ir_flash_start", 0.0) > FLASH_DURATION
        ):
            receipt = state.pop("ir_flash_receipt", EffectReceipt)
            state.delete("ir_flash_start")
            state.effect_controls.stop_effect_by_receipt(receipt)
            state.effect_controls.set_effect(
                Scope.DIRECTIONAL, "basic.solid", 3, {"color": 0xFFFFFF}
            )

        if (
            "radio_flash_start" in state
            and state.total - state.get("radio_flash_start", 0.0) > FLASH_DURATION
        ):
            receipt = state.pop("radio_flash_receipt", EffectReceipt)
            state.delete("radio_flash_start")
            state.effect_controls.stop_effect_by_receipt(receipt)
            state.effect_controls.set_effect(
                Scope.Global.ALL, "basic.solid", 3, {"color": 0xFFFFFF}
            )


RULE = HwTestModeRule()
