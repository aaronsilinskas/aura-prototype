"""IR range transmitter rule — fixed-rate, sequence-numbered IR sends on LINE.

The sequence counter and last-send time are scene data held in ``GameState``
(``_SEQUENCE_KEY``/``_LAST_SEND_KEY``), not rule instance state -- this rule
holds no mutable attributes of its own beyond the ``on()`` registration done
at construction.

The rule-facing ``NetworkControls`` seam is send-only (no ``busy`` check), so
time-gating on ``state.total`` is the whole rate-control mechanism. On real
hardware a send blocks for the whole frame, so frame length also caps the
achievable rate whatever ``send_rate_hz`` asks for.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.network import LINE
from engine.state import GameState
from packs.scenes.ir_range_transmitter.rules.helpers.transmitter_config import (
    transmitter_config,
)

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

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
