"""``IrRangeConfig`` -- the ir_range_receiver Scene Config.

Holds the scene's three Settings, declared in its ``scene.json``: the
rolling-window length and silence timeout the ``ReceptionQualityMeter`` uses,
and the green threshold that decides how strict "Perfect" reception must be.
``IrRangeConfig`` is built from the scene's Settings view.

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

from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "ir_range_config"


class IrRangeConfig:
    """Immutable configuration for the ir_range_receiver scene, each field
    read from the scene Setting of the same name."""

    __slots__ = ("green_threshold", "silence_timeout", "window_seconds")

    def __init__(self, settings: Settings) -> None:
        self.window_seconds = settings.get_float(SCENE_NAMESPACE, "window_seconds")
        self.silence_timeout = settings.get_float(SCENE_NAMESPACE, "silence_timeout")
        self.green_threshold = settings.get_float(SCENE_NAMESPACE, "green_threshold")


def _from_state(state: GameState) -> IrRangeConfig:
    return IrRangeConfig(state.settings)


ir_range_config = StateSlot(_CONFIG_KEY, _from_state, IrRangeConfig)
