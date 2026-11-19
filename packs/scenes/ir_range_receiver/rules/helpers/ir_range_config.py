from __future__ import annotations

from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

_CONFIG_KEY: Final = "ir_range_config"


class IrRangeConfig:
    __slots__ = ("green_threshold", "silence_timeout", "window_seconds")

    def __init__(self, settings: Settings) -> None:
        self.window_seconds = settings.get_float(SCENE_NAMESPACE, "window_seconds")
        self.silence_timeout = settings.get_float(SCENE_NAMESPACE, "silence_timeout")
        self.green_threshold = settings.get_float(SCENE_NAMESPACE, "green_threshold")


def _from_state(state: GameState) -> IrRangeConfig:
    return IrRangeConfig(state.settings)


ir_range_config = StateSlot(_CONFIG_KEY, _from_state, IrRangeConfig)
