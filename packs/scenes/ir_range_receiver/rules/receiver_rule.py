"""ir_range_receiver scene rule -- paints IR link quality as a pixel meter.

A single scene-local plain ``GameRule`` (the ``element_browser`` shape -- no
phase machine): it records every ``NetworkEvents.IRReceived`` arrival and, on
the per-tick ``InputEvents.Sensors`` heartbeat, asks the pure
``ReceptionQualityMeter`` to recompute reception quality and applies its
silence timeout. The heartbeat is required for silence detection --
``IRReceived`` alone can never signal "packets stopped", since no event fires
when transmission goes quiet.

Rendering is a single effect on ``Scope.NON_AMBIENT``, re-issued only when the
displayed state changes -- an already-issued effect persists, so this is an
optimization, not a correctness requirement.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # Not available on all embedded runtimes

from engine.engine import GameRule
from engine.input import InputEvents
from engine.network import NetworkEvents
from engine.state import GameState, Scope
from packs.scenes.ir_range_receiver.rules.helpers.ir_range_meter import ir_range_meter
from packs.scenes.ir_range_receiver.rules.helpers.reception_quality_meter import (
    STATE_PARTIAL,
    ReceptionQuality,
)

_LAST_STATE_KEY: Final = "ir_range_last_state"
_NEXT_PRINT_KEY: Final = "ir_range_next_print"
_PRINT_INTERVAL: Final = 1.0


class IrRangeReceiverRule(GameRule):
    """Renders a green/yellow/red pixel meter from IR reception quality."""

    def __init__(self) -> None:
        self.on(NetworkEvents.IRReceived, self._on_ir_received)
        self.on(InputEvents.Sensors, self._on_sensors)

    def _on_ir_received(self, event: NetworkEvents.IRReceived, state: GameState) -> None:
        # Byte 0 is the sequence number; every other field (signal_strength,
        # error_margin, best_receiver) is telemetry the meter has no use for --
        # in particular, best_receiver varies freely with an IR multi-receiver
        # (multiple rx pins) without affecting reception quality at all.
        ir_range_meter(state).record(event.data[0], state.total)

    def _on_sensors(self, event: InputEvents.Sensors, state: GameState) -> None:
        quality = ir_range_meter(state).evaluate(state.total)

        if state.get(_LAST_STATE_KEY, None) != quality.state:
            state.set(_LAST_STATE_KEY, quality.state)
            self._render(quality, state)

        self._maybe_print(quality, state)

    def _render(self, quality: ReceptionQuality, state: GameState) -> None:
        if quality.state == STATE_PARTIAL:
            state.effect_controls.set_effect(
                Scope.NON_AMBIENT,
                "basic.progress",
                {"progress": quality.progress, "color": quality.color},
            )
        else:
            state.effect_controls.set_effect(
                Scope.NON_AMBIENT, "basic.solid", {"color": quality.color}
            )

    def _maybe_print(self, quality: ReceptionQuality, state: GameState) -> None:
        if state.total < state.get(_NEXT_PRINT_KEY, 0.0):
            return
        state.set(_NEXT_PRINT_KEY, state.total + _PRINT_INTERVAL)
        print(
            "[ir_range state="
            + quality.state
            + " rate="
            + str(quality.progress)
            + " received="
            + str(quality.received)
            + " dropped="
            + str(quality.dropped)
            + "]"
        )


RULE = IrRangeReceiverRule()
