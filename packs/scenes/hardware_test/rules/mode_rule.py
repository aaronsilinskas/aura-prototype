from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import IR_FLASH_KEY, RADIO_FLASH_KEY, flash
from packs.scenes.hardware_test.rules.helpers.mode import _RGB_IDLE, NUM_MODES, current_mode

FLASH_DURATION: Final = 0.5


def _enter_rgb(state: GameState) -> None:
    ec = state.effect_controls
    state.set("rgb_level", 1)
    for scope, name in _RGB_IDLE:
        ec.set_effect(scope, name, {"level": 1})


def _enter_accelerometer(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.PERSONAL, "basic.progress", {"color": 0xFF0000, "progress": 0.0})
    ec.set_effect(Scope.DIRECTIONAL, "basic.progress", {"color": 0x00FF00, "progress": 0.0})
    ec.set_effect(Scope.Global.ALL, "basic.progress", {"color": 0x0000FF, "progress": 0.0})


def _enter_ir(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.ALL, "basic.solid", {"color": 0xFFFFFF})


def _enter_radio(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.ALL, "basic.solid", {"color": 0xFFFFFF})


def _enter_sfx(state: GameState) -> None:
    ec = state.effect_controls
    ec.set_effect(Scope.PERSONAL, "basic.solid", {"color": 0x00FFFF})


_MODE_ENTRY: Final = (_enter_rgb, _enter_accelerometer, _enter_ir, _enter_radio, _enter_sfx)


class HwTestModeRule(GameRule):
    """Drives hardware_test mode transitions: entry effects, Button B, flash expiry.

    Per-mode Button A behaviour lives in each mode's owning rule (``rgb_rule``,
    ``network_rule``, ``sfx_rule``); this rule only dispatches one-time mode
    entry effects, advances the mode on Button B, logs the change, and expires
    the IR/radio receive flashes.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        # Fire mode-entry effects once on load. ``hw_mode`` is seeded into
        # ``initial_data``, so a separate ``hw_entered`` flag (not the presence
        # of ``hw_mode``) marks whether entry effects have run.
        if "hw_entered" not in state:
            state.set("hw_entered", True)
            _MODE_ENTRY[current_mode(state)](state)

        self._check_flash_expiry(state)

        if event.buttons.is_pressed("B"):
            self._advance_mode(state)

    def _advance_mode(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)
        # Clear all flash keys
        state.delete(IR_FLASH_KEY)
        state.delete(RADIO_FLASH_KEY)

        new_mode = (current_mode(state) + 1) % NUM_MODES
        print("changing to mode " + str(new_mode))
        state.set("hw_mode", new_mode)
        _MODE_ENTRY[new_mode](state)

    def _check_flash_expiry(self, state: GameState) -> None:
        self._expire_flash(state, IR_FLASH_KEY, Scope.DIRECTIONAL)
        self._expire_flash(state, RADIO_FLASH_KEY, Scope.Global.ALL)

    def _expire_flash(self, state: GameState, key: str, idle_scope: Scope) -> None:
        if not state.has(key):
            return

        flash_state = flash(state, key)
        if not flash_state.expired(state.total, FLASH_DURATION):
            return

        receipt = flash_state.receipt
        state.delete(key)
        receipt.stop()
        state.effect_controls.set_effect(idle_scope, "basic.solid", {"color": 0xFFFFFF})


RULE = HwTestModeRule()
