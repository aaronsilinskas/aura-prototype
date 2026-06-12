"""Scene-local ``PhaseRule`` base shared by the five hardware_test mode rules.

Each hardware_test mode (RGB, Accelerometer, IR, Radio, SFX) is a
:class:`HwModeRule` subclass: a :class:`~engine.phase.PhaseRule` bound to the
scene's shared :func:`hw_phase` machine. Because the override-``on()`` model
in :mod:`engine.phase` dispatches one handler per event type, this base
registers the single ``ButtonAndAcceleration`` handler for all five modes and
uses a template method: :meth:`_handle` calls :meth:`on_input_event` (each
mode overrides) with the whole event for per-mode logic, then performs the
behaviour every mode shares — Button B advances to the next mode in
:data:`MODE_ORDER`, and the IR/radio receive-flash expiry is checked every
tick.

``on_input_event`` is scene-local: it is not a general ``on_event`` and is
only ever called for ``ButtonAndAcceleration`` events.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.input import InputEvents
from engine.phase import PhaseKey, PhaseMachine, PhaseRule
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.flash import IR_FLASH_KEY, RADIO_FLASH_KEY, flash
from packs.scenes.hardware_test.rules.helpers.phases import (
    HW_MACHINE_KEY,
    MODE_ORDER,
    MODE_RGB,
    hw_phase,
    next_in_cycle,
)

FLASH_DURATION: Final = 0.5

# Set by _advance_mode to (PhaseKey just transitioned to, state.total at the
# time of the transition), and consumed by the newly-entered mode's own
# _handle if it is dispatched again within the *same* tick (its rule comes
# after the advancing rule in registration order). The state.total stamp
# distinguishes this from a stale entry left over from a previous tick (when
# the newly-entered mode's rule had already been dispatched and so never saw
# the new phase until the next tick) — a stale entry's stamp won't match the
# current tick's state.total, so it is never mistaken for "skip this
# dispatch".
_ADVANCED_TO_KEY: Final = "hw_mode_advanced_to"


class HwModeRule(PhaseRule):
    """A :class:`PhaseRule` bound to the hardware_test scene's shared phase machine.

    Subclasses provide ``on_enter`` (the mode's one-time entry effect) and
    :meth:`on_input_event` (the mode's per-tick/per-button behaviour). This
    base owns the Button-B "advance to next mode" transition and the
    IR/radio receive-flash expiry, both of which run on every dispatch
    regardless of which button (if any) was pressed.
    """

    def __init__(self, phase: PhaseKey) -> None:
        super().__init__(phase, HW_MACHINE_KEY, MODE_RGB)
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _machine(self, state: GameState) -> PhaseMachine:
        return hw_phase(state)

    def on_input_event(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        """Per-mode handling of the whole input event. No-op by default."""

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        # Consume any pending advance marker stamped during *this* tick. If it
        # targets this mode, a Button-B advance just transitioned into this
        # mode within this same dispatch (see _advance_mode); this dispatch is
        # a continuation of that one press, not a fresh tick, so skip it
        # entirely. A marker stamped during a previous tick (left over because
        # the newly-entered mode's rule had already been dispatched that tick)
        # is stale and is simply discarded without skipping.
        advanced = state.get(_ADVANCED_TO_KEY, None)
        if advanced is not None:
            advanced_to, advanced_at = advanced
            state.delete(_ADVANCED_TO_KEY)
            if advanced_to is self.phase and advanced_at == state.total:
                return

        self.on_input_event(event, state)

        self._check_flash_expiry(state)

        if event.buttons.is_pressed("B"):
            self._advance_mode(state)

    def _advance_mode(self, state: GameState) -> None:
        state.effect_controls.stop_effect(Scope.ALL)
        # Clear all flash keys
        state.delete(IR_FLASH_KEY)
        state.delete(RADIO_FLASH_KEY)

        next_mode = next_in_cycle(MODE_ORDER, self.phase)
        print("changing to mode " + str(MODE_ORDER.index(next_mode)))
        state.set(_ADVANCED_TO_KEY, (next_mode, state.total))
        self.transition_to(state, next_mode)

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
        assert receipt is not None  # expired() is only True once restart() set a receipt
        state.delete(key)
        receipt.stop()
        state.effect_controls.set_effect(idle_scope, "basic.solid", {"color": 0xFFFFFF})
