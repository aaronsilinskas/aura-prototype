from __future__ import annotations

from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_CONFIG_KEY: Final = "irtx_config"

# Byte i (i >= 1) carries 0xA0 | (i & 0x0F), so the encoded frame is never a
# degenerate run of zeros.
_PADDING_MARKER_BASE: Final = 0xA0
_PADDING_MARKER_MASK: Final = 0x0F


def _build_payload_padding(payload_size: int) -> bytes:
    return bytes(_PADDING_MARKER_BASE | (i & _PADDING_MARKER_MASK) for i in range(1, payload_size))


class TransmitterConfig:
    __slots__ = ("payload_padding", "payload_size", "send_period_seconds", "send_rate_hz")

    def __init__(self, settings: Settings) -> None:
        self.send_rate_hz = settings.get_float(SCENE_NAMESPACE, "send_rate_hz")
        self.payload_size = settings.get_int(SCENE_NAMESPACE, "payload_size")
        self.send_period_seconds = 1.0 / self.send_rate_hz
        self.payload_padding = _build_payload_padding(self.payload_size)


def _from_state(state: GameState) -> TransmitterConfig:
    return TransmitterConfig(state.settings)


transmitter_config = StateSlot(_CONFIG_KEY, _from_state, TransmitterConfig)
