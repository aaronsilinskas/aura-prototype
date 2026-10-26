"""Scene-local ``PhaseRule`` base shared by the six hardware_test mode rules.

Each hardware_test mode (RGB, Accelerometer, Magnetometer, IR, Radio, SFX) is
a :class:`HwModeRule` subclass: a :class:`~engine.phase.PhaseRule` bound to
the scene's shared :func:`hw_phase` machine. Because the override-``on()``
model in :mod:`engine.phase` dispatches one handler per event type, this base
registers the single ``Sensors`` handler for all six modes and
uses a template method: :meth:`_handle` calls :meth:`on_input_event` (each
mode overrides) with the whole event for per-mode logic, then performs the
behaviour every mode shares — Button B advances to the next mode in
:data:`MODE_ORDER`, and the IR/radio receive-flash expiry is checked every
tick.

``on_input_event`` is scene-local: it is not a general ``on_event`` and is
only ever called for ``Sensors`` events.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.input import InputEvents
from engine.phase import PhaseKey, PhaseRule
from engine.state import GameState, Scope, ScopeValue, StateSlot
from packs.scenes.hardware_test.rules.helpers.flash import ir_flash, radio_flash
from packs.scenes.hardware_test.rules.helpers.phases import (
    MODE_ORDER,
    hw_phase,
    next_in_cycle,
)

FLASH_DURATION: Final = 0.5


class HwModeRule(PhaseRule):
    """A :class:`PhaseRule` bound to the hardware_test scene's shared phase machine.

    Subclasses provide ``on_enter`` (the mode's one-time entry effect) and
    :meth:`on_input_event` (the mode's per-tick/per-button behaviour). This
    base owns the Button-B "advance to next mode" transition and the
    IR/radio receive-flash expiry, both of which run on every dispatch
    regardless of which button (if any) was pressed.
    """

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, hw_phase)
        self.on(InputEvents.Sensors, self._handle)

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        """Per-mode handling of the whole input event. No-op by default."""

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        self.on_input_event(event, state)

        self._check_flash_expiry(state)

        if event.buttons.is_pressed("B"):
            self._advance_mode(state)

    def _advance_mode(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)
        # Clear all flash keys
        state.delete(ir_flash.key)
        state.delete(radio_flash.key)

        next_mode = next_in_cycle(MODE_ORDER, self.phase)
        print("changing to mode " + str(MODE_ORDER.index(next_mode)))
        self.transition_to(state, next_mode)

    def _check_flash_expiry(self, state: GameState) -> None:
        self._expire_flash(state, ir_flash, Scope.DIRECTIONAL)
        self._expire_flash(state, radio_flash, Scope.Global.ALL)

    def _expire_flash(self, state: GameState, slot: StateSlot, idle_scope: ScopeValue) -> None:
        if not slot.is_in(state):
            return

        flash_state = slot(state)
        if not flash_state.expired(state.total, FLASH_DURATION):
            return

        receipt = flash_state.receipt
        assert receipt is not None  # expired() is only True once restart() set a receipt
        state.delete(slot.key)
        receipt.stop()
        state.effect_controls.set_effect(idle_scope, "basic.solid", {"color": 0xFFFFFF})
