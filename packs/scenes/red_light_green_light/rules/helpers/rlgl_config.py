"""``RlglConfig`` — immutable scene configuration for Red Light Green Light.

Holds the duration/threshold knobs tunable via ``initial_data`` (all ``rlgl_``
seed keys).  ``RlglConfig.__init__`` takes already-resolved values so it is
unit-testable directly with no ``GameState`` involved; ``from_state`` is the
factory that reads the flat seeded ``rlgl_*`` keys and applies defaults.

``rlgl_config`` is a :class:`engine.state.StateSlot` callable accessor: it lazily
builds the config from ``state`` on first use and caches it under a single
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
from engine.state import GameState, StateSlot
from packs.scenes.red_light_green_light.rules.helpers.motion_detector import (
    GRAVITY_LOWPASS_BETA,
    MOTION_EMA_ALPHA,
)

_CONFIG_KEY: Final = "rlgl_config"

# Level-1 warning pulse sub-duration ratios (brighten / on / darken = 0.3 / 0.4 / 0.3)
_WARNING_BRIGHTEN_RATIO: Final = 0.3
_WARNING_ON_RATIO: Final = 0.4
_WARNING_DARKEN_RATIO: Final = 0.3


class RlglConfig:
    """Immutable duration/threshold configuration for the RLGL scene.

    All values are already-resolved (no ``GameState`` knowledge), so this can
    be constructed directly in tests.  Use :meth:`from_state` to build one
    from a seeded ``GameState``.
    """

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

    def __init__(
        self,
        red_duration_max: float,
        red_duration_min: float,
        green_duration_max: float,
        green_duration_min: float,
        warning_pulse_max: float,
        warning_pulse_min: float,
        game_over_duration: float,
        green_still_timeout: float,
        level_up_duration: float,
        max_level: int,
        motion_smoothing: float,
        gravity_beta: float,
    ) -> None:
        self.red_duration_max = red_duration_max
        self.red_duration_min = red_duration_min
        self.green_duration_max = green_duration_max
        self.green_duration_min = green_duration_min
        self.warning_pulse_max = warning_pulse_max
        self.warning_pulse_min = warning_pulse_min
        self.game_over_duration = game_over_duration
        self.green_still_timeout = green_still_timeout
        self.level_up_duration = level_up_duration
        self.max_level = max_level
        self.motion_smoothing = motion_smoothing
        self.gravity_beta = gravity_beta

    @classmethod
    def from_state(cls, state: GameState) -> RlglConfig:
        """Build a config from the flat seeded ``rlgl_*`` keys, applying defaults."""
        return cls(
            red_duration_max=state.get("rlgl_red_duration", 5.0),
            red_duration_min=state.get("rlgl_red_duration_min", 2.0),
            green_duration_max=state.get("rlgl_green_duration", 5.0),
            green_duration_min=state.get("rlgl_green_duration_min", 2.0),
            warning_pulse_max=state.get("rlgl_warning_pulse_max", 1.0),
            warning_pulse_min=state.get("rlgl_warning_pulse_min", 0.4),
            game_over_duration=state.get("rlgl_game_over_duration", 3.0),
            green_still_timeout=state.get("rlgl_green_still_timeout", 0.75),
            level_up_duration=state.get("rlgl_level_up_duration", 1.0),
            max_level=state.get("rlgl_max_level", 10),
            motion_smoothing=state.get("rlgl_motion_smoothing", MOTION_EMA_ALPHA),
            gravity_beta=state.get("rlgl_gravity_beta", GRAVITY_LOWPASS_BETA),
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


rlgl_config: StateSlot = StateSlot(_CONFIG_KEY, RlglConfig.from_state, RlglConfig)
