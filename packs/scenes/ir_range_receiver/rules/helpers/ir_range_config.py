"""``IrRangeConfig`` -- the ir_range_receiver Scene Config.

Holds the scene's three Settings, declared in its ``scene.json``: the
rolling-window length and silence timeout the ``ReceptionQualityMeter`` uses,
and the green threshold that decides how strict "Perfect" reception must be.
``IrRangeConfig.__init__`` takes already-resolved values so it is
unit-testable directly; ``from_settings`` builds one from the Settings view.

``ir_range_config`` is a :class:`engine.state.StateSlot` callable accessor: it
lazily builds the config from ``state.settings`` on first use and caches it
under a single ``GameState`` key, mirroring the ``rlgl_config``/``tag_config``
precedent.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.settings import Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "ir_range_config"

NAMESPACE: Final = "scene"


class IrRangeConfig:
    """Immutable configuration for the ir_range_receiver scene.

    All values are already-resolved, so this can be constructed directly in
    tests. Use :meth:`from_settings` to build one from the scene's Settings.
    """

    __slots__ = ("green_threshold", "silence_timeout", "window_seconds")

    def __init__(
        self, window_seconds: float, silence_timeout: float, green_threshold: float
    ) -> None:
        self.window_seconds = window_seconds
        self.silence_timeout = silence_timeout
        self.green_threshold = green_threshold

    @classmethod
    def from_settings(cls, settings: Settings) -> IrRangeConfig:
        """Build a config from the scene's Settings, each named as its field."""
        return cls(
            window_seconds=settings.get_float(NAMESPACE, "window_seconds"),
            silence_timeout=settings.get_float(NAMESPACE, "silence_timeout"),
            green_threshold=settings.get_float(NAMESPACE, "green_threshold"),
        )


def _from_state(state: GameState) -> IrRangeConfig:
    return IrRangeConfig.from_settings(state.settings)


ir_range_config: StateSlot = StateSlot(_CONFIG_KEY, _from_state, IrRangeConfig)
