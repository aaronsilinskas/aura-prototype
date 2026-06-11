"""``TagConfig`` — immutable scene configuration for the Tag scene.

Holds the tunables seeded via ``initial_data`` (all ``tag_*`` seed keys).
``TagConfig.__init__`` takes already-resolved values so it is unit-testable
directly with no ``GameState`` involved; ``from_state`` is the factory that
reads the flat seeded ``tag_*`` keys and applies defaults.

``tag_config(state)`` is the get-or-create accessor: it lazily builds the
config from ``state`` on first use and caches it under a single ``GameState``
key, mirroring the ``rlgl_config(state)`` precedent in the
red_light_green_light scene.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState

_CONFIG_KEY: Final = "tag_config"

DEFAULT_STARTING_HITPOINTS: Final = 10
DEFAULT_DEAFEN_WINDOW: Final = 0.1
DEFAULT_EXPECTED_TEAM: Final = 0
DEFAULT_EXPECTED_PLAYER: Final = 1
DEFAULT_WARNING_PULSE_COUNT: Final = 5
DEFAULT_WARNING_PULSE_DURATION: Final = 0.6


class TagConfig:
    """Immutable tunable configuration for the Tag scene.

    All values are already-resolved (no ``GameState`` knowledge), so this can
    be constructed directly in tests. Use :meth:`from_state` to build one
    from a seeded ``GameState``.
    """

    __slots__ = (
        "deafen_window",
        "expected_player",
        "expected_team",
        "starting_hitpoints",
        "warning_pulse_count",
        "warning_pulse_duration",
    )

    def __init__(
        self,
        starting_hitpoints: int,
        deafen_window: float,
        expected_team: int,
        expected_player: int,
        warning_pulse_count: int,
        warning_pulse_duration: float,
    ) -> None:
        self.starting_hitpoints = starting_hitpoints
        self.deafen_window = deafen_window
        self.expected_team = expected_team
        self.expected_player = expected_player
        self.warning_pulse_count = warning_pulse_count
        self.warning_pulse_duration = warning_pulse_duration

    @classmethod
    def from_state(cls, state: GameState) -> TagConfig:
        """Build a config from the flat seeded ``tag_*`` keys, applying defaults."""
        return cls(
            starting_hitpoints=state.get("tag_starting_hitpoints", DEFAULT_STARTING_HITPOINTS),
            deafen_window=state.get("tag_deafen_window", DEFAULT_DEAFEN_WINDOW),
            expected_team=state.get("tag_expected_team", DEFAULT_EXPECTED_TEAM),
            expected_player=state.get("tag_expected_player", DEFAULT_EXPECTED_PLAYER),
            warning_pulse_count=state.get("tag_warning_pulse_count", DEFAULT_WARNING_PULSE_COUNT),
            warning_pulse_duration=state.get(
                "tag_warning_pulse_duration", DEFAULT_WARNING_PULSE_DURATION
            ),
        )

    def warning_duration(self) -> float:
        """Return the total Starting countdown duration = pulse count x pulse duration."""
        return self.warning_pulse_count * self.warning_pulse_duration


def tag_config(state: GameState) -> TagConfig:
    """Return the cached :class:`TagConfig`, building and caching it on first use."""
    if not state.has(_CONFIG_KEY):
        state.set(_CONFIG_KEY, TagConfig.from_state(state))
    return state.get(_CONFIG_KEY, None)
