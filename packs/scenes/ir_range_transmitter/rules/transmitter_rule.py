"""IR range transmitter rule — fixed-rate, sequence-numbered IR sends on LINE.

A plain, phase-less ``GameRule`` (the ``element_browser`` shape): on every
per-tick ``InputEvents.Sensors`` heartbeat it time-gates on ``state.total``
against ``TransmitterConfig.send_period_seconds``. Once a send period has
elapsed since the last send, it writes the next sequence number into byte 0
of a fresh payload (padding bytes carry ``TransmitterConfig.payload_padding``,
a fixed non-zero marker so the encoded frame is never a degenerate run of
zeros) and sends it via ``state.network_controls.send_ir`` on ``LINE``.

The sequence counter and last-send time are scene data held in ``GameState``
(``_SEQUENCE_KEY``/``_LAST_SEND_KEY``), not rule instance state -- this rule
holds no mutable attributes of its own beyond the ``on()`` registration done
at construction.

The rule-facing ``NetworkControls`` seam is send-only (no ``busy`` check), so
time-gating on ``state.total`` is the whole rate-control mechanism -- see the
module docstring in ``ir_rx_packet_source.py`` for why a 4-byte send's
blocking duration on real hardware caps the ceiling regardless.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule
from engine.input import InputEvents
from engine.network import LINE
from engine.state import GameState
from packs.scenes.ir_range_transmitter.rules.helpers.transmitter_config import (
    transmitter_config,
)

_SEQUENCE_KEY: Final = "irtx_sequence"
_LAST_SEND_KEY: Final = "irtx_last_send_total"

_SEQUENCE_WRAP: Final = 256


class IrRangeTransmitterRule(GameRule):
    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        config = transmitter_config(state)

        last_send = state.get_or_none(_LAST_SEND_KEY, float)
        if last_send is not None and state.total - last_send < config.send_period_seconds:
            return

        sequence = state.get(_SEQUENCE_KEY, 0)
        payload = bytearray(config.payload_size)
        payload[0] = sequence
        payload[1:] = config.payload_padding

        state.network_controls.send_ir(bytes(payload), LINE)

        state.set(_SEQUENCE_KEY, (sequence + 1) % _SEQUENCE_WRAP)
        state.set(_LAST_SEND_KEY, state.total)


RULE = IrRangeTransmitterRule()
