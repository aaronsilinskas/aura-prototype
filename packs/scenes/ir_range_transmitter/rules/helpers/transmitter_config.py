"""``TransmitterConfig`` — the IR range transmitter's Scene Config.

Holds the scene's Settings, declared in its ``scene.json``, and the values
derived from them. ``TransmitterConfig.__init__`` takes already-resolved
values so it is unit-testable directly; ``from_settings`` builds one from the
Settings view.

``transmitter_config`` is a :class:`engine.state.StateSlot` callable accessor:
it lazily builds the config from ``state.settings`` on first use and caches it
under a single ``GameState`` key, mirroring the ``rlgl_config``/``tag_config``
precedent in the red_light_green_light and tag scenes.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "irtx_config"

# Fixed non-zero padding marker: byte i
# (i >= 1) carries 0xA0 | (i & 0x0F), so the encoded frame is never a
# degenerate run of zeros.
_PADDING_MARKER_BASE: Final = 0xA0
_PADDING_MARKER_MASK: Final = 0x0F


def _build_payload_padding(payload_size: int) -> bytes:
    """Return the fixed non-zero padding tail for bytes ``1..payload_size - 1``."""
    return bytes(_PADDING_MARKER_BASE | (i & _PADDING_MARKER_MASK) for i in range(1, payload_size))


class TransmitterConfig:
    """Immutable configuration for the IR range transmitter scene.

    All values are already-resolved, so this can be constructed directly in
    tests. Use :meth:`from_settings` to build one from the scene's Settings.
    """

    __slots__ = ("payload_padding", "payload_size", "send_period_seconds", "send_rate_hz")

    def __init__(self, send_rate_hz: float, payload_size: int) -> None:
        self.send_rate_hz = send_rate_hz
        self.payload_size = payload_size
        self.send_period_seconds = 1.0 / send_rate_hz
        self.payload_padding = _build_payload_padding(payload_size)

    @classmethod
    def from_settings(cls, settings: Settings) -> TransmitterConfig:
        """Build a config from the scene's Settings, each named as its field."""
        return cls(
            send_rate_hz=settings.get_float(SCENE_NAMESPACE, "send_rate_hz"),
            payload_size=settings.get_int(SCENE_NAMESPACE, "payload_size"),
        )


def _from_state(state: GameState) -> TransmitterConfig:
    return TransmitterConfig.from_settings(state.settings)


transmitter_config: StateSlot = StateSlot(_CONFIG_KEY, _from_state, TransmitterConfig)
