"""``RlglConfig`` — the Red Light Green Light Scene Config.

Holds the scene's twelve Settings, declared in its ``scene.json``.

``rlgl_config`` is a :class:`engine.state.StateSlot` callable accessor: it lazily
builds the config from ``state.settings`` on first use and caches it under a single
``GameState`` key, mirroring the ``current_mode(state)`` precedent in the
hardware_test scene.  Game Level is read separately each tick (it changes during play), so
the level-scaled methods below take ``level`` as a parameter and the config
itself stays immutable and level-agnostic.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.lerp import level_lerp
from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "rlgl_config"

# Level-1 warning pulse sub-duration ratios (brighten / on / darken = 0.3 / 0.4 / 0.3)
_WARNING_BRIGHTEN_RATIO: Final = 0.3
_WARNING_ON_RATIO: Final = 0.4
_WARNING_DARKEN_RATIO: Final = 0.3


class RlglConfig:
    """Immutable duration/threshold configuration for the RLGL scene, each
    field read from the scene Setting of the same name."""

    __slots__ = (
        "game_over_duration",
        "gravity_beta",
        "green_duration_max",
        "green_duration_min",
        "green_still_timeout",
        "level_up_duration",
        "max_level",
        "motion_smoothing",
        "red_duration_max",
        "red_duration_min",
        "warning_pulse_max",
        "warning_pulse_min",
    )

    def __init__(self, settings: Settings) -> None:
        """Read the scene's Settings, checking they agree.

        Raises:
            ValueError: ``gravity_beta`` is not below ``motion_smoothing``, so
                real motion would be absorbed into the gravity estimate.
        """
        self.red_duration_max = settings.get_float(SCENE_NAMESPACE, "red_duration_max")
        self.red_duration_min = settings.get_float(SCENE_NAMESPACE, "red_duration_min")
        self.green_duration_max = settings.get_float(SCENE_NAMESPACE, "green_duration_max")
        self.green_duration_min = settings.get_float(SCENE_NAMESPACE, "green_duration_min")
        self.warning_pulse_max = settings.get_float(SCENE_NAMESPACE, "warning_pulse_max")
        self.warning_pulse_min = settings.get_float(SCENE_NAMESPACE, "warning_pulse_min")
        self.game_over_duration = settings.get_float(SCENE_NAMESPACE, "game_over_duration")
        self.green_still_timeout = settings.get_float(SCENE_NAMESPACE, "green_still_timeout")
        self.level_up_duration = settings.get_float(SCENE_NAMESPACE, "level_up_duration")
        self.max_level = settings.get_int(SCENE_NAMESPACE, "max_level")
        self.motion_smoothing = settings.get_float(SCENE_NAMESPACE, "motion_smoothing")
        self.gravity_beta = settings.get_float(SCENE_NAMESPACE, "gravity_beta")
        if self.gravity_beta >= self.motion_smoothing:
            raise ValueError(
                f"gravity_beta ({self.gravity_beta}) must be below"
                + f" motion_smoothing ({self.motion_smoothing})"
            )

    def red_duration(self, level: int) -> float:
        """Return the red phase duration scaled by Game Level."""
        return level_lerp(level, self.red_duration_max, self.red_duration_min, self.max_level)

    def green_duration(self, level: int) -> float:
        """Return the green phase duration scaled by Game Level."""
        return level_lerp(level, self.green_duration_max, self.green_duration_min, self.max_level)

    def warning_pulse_duration(self, level: int) -> float:
        """Return the warning pulse duration (seconds) scaled by Game Level."""
        return level_lerp(level, self.warning_pulse_max, self.warning_pulse_min, self.max_level)

    def warning_duration(self, level: int) -> float:
        """Return the warning phase duration = 3 x pulse_duration(level)."""
        return 3.0 * self.warning_pulse_duration(level)

    def warning_sting_opts(self, level: int) -> dict[str, object]:
        """Build warning sting options with sub-durations scaled to the pulse duration."""
        pulse = self.warning_pulse_duration(level)
        return {
            "start_color": 0x000000,
            "end_color": 0xFFFF00,
            "brighten_duration": pulse * _WARNING_BRIGHTEN_RATIO,
            "on_duration": pulse * _WARNING_ON_RATIO,
            "darken_duration": pulse * _WARNING_DARKEN_RATIO,
            "off_duration": 0.0,
        }


def _from_state(state: GameState) -> RlglConfig:
    return RlglConfig(state.settings)


rlgl_config = StateSlot(_CONFIG_KEY, _from_state, RlglConfig)
