"""``TransmitterConfig`` — immutable scene configuration for the IR range transmitter.

Holds the tunables seeded via ``initial_data`` (all ``irtx_`` seed keys).
``TransmitterConfig.__init__`` takes already-resolved values so it is
unit-testable directly with no ``GameState`` involved; ``from_state`` is the
factory that reads the flat seeded ``irtx_*`` keys and applies defaults.

``transmitter_config`` is a :class:`engine.state.StateSlot` callable accessor:
it lazily builds the config from ``state`` on first use and caches it under a
single ``GameState`` key, mirroring the ``rlgl_config``/``tag_config``
precedent in the red_light_green_light and tag scenes.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "irtx_config"

_DEFAULT_SEND_RATE_HZ: Final = 5.0
_DEFAULT_PAYLOAD_SIZE: Final = 4

# Fixed non-zero padding marker, matching ir_rx_packet_source.py: byte i
# (i >= 1) carries 0xA0 | (i & 0x0F), so the encoded frame is never a
# degenerate run of zeros.
_PADDING_MARKER_BASE: Final = 0xA0
_PADDING_MARKER_MASK: Final = 0x0F


def _build_payload_padding(payload_size: int) -> bytes:
    """Return the fixed non-zero padding tail for bytes ``1..payload_size - 1``."""
    return bytes(_PADDING_MARKER_BASE | (i & _PADDING_MARKER_MASK) for i in range(1, payload_size))


class TransmitterConfig:
    """Immutable tunable configuration for the IR range transmitter scene.

    All values are already-resolved (no ``GameState`` knowledge), so this can
    be constructed directly in tests. Use :meth:`from_state` to build one
    from a seeded ``GameState``.
    """

    __slots__ = ("payload_padding", "payload_size", "send_period_seconds", "send_rate_hz")

    def __init__(self, send_rate_hz: float, payload_size: int) -> None:
        self.send_rate_hz = send_rate_hz
        self.payload_size = payload_size
        self.send_period_seconds = 1.0 / send_rate_hz
        self.payload_padding = _build_payload_padding(payload_size)

    @classmethod
    def from_state(cls, state: GameState) -> TransmitterConfig:
        """Build a config from the flat seeded ``irtx_*`` keys, applying defaults."""
        return cls(
            send_rate_hz=state.get("irtx_send_rate_hz", _DEFAULT_SEND_RATE_HZ),
            payload_size=state.get("irtx_payload_size", _DEFAULT_PAYLOAD_SIZE),
        )


transmitter_config: StateSlot = StateSlot(
    _CONFIG_KEY, TransmitterConfig.from_state, TransmitterConfig
)
