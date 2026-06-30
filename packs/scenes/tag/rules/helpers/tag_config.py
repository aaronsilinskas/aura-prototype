"""``TagConfig`` — immutable scene configuration for the Tag scene.

Holds the tunables seeded via ``initial_data`` (all ``tag_*`` seed keys).
``TagConfig.__init__`` takes already-resolved values so it is unit-testable
directly with no ``GameState`` involved; ``from_state`` is the factory that
reads the flat seeded ``tag_*`` keys and applies defaults.

``tag_config`` is a :class:`engine.state.StateSlot` callable accessor: it lazily
builds the config from ``state`` on first use and caches it under a single
``GameState`` key, mirroring the ``rlgl_config`` precedent in the
red_light_green_light scene.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "tag_config"


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
        "max_ammo",
        "reload_duration",
        "shot_cooldown",
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
        max_ammo: int,
        shot_cooldown: float,
        reload_duration: float,
    ) -> None:
        self.starting_hitpoints = starting_hitpoints
        self.deafen_window = deafen_window
        self.expected_team = expected_team
        self.expected_player = expected_player
        self.warning_pulse_count = warning_pulse_count
        self.warning_pulse_duration = warning_pulse_duration
        self.max_ammo = max_ammo
        self.shot_cooldown = shot_cooldown
        self.reload_duration = reload_duration

    @classmethod
    def from_state(cls, state: GameState) -> TagConfig:
        """Build a config from the flat seeded ``tag_*`` keys, applying defaults."""
        return cls(
            starting_hitpoints=state.get("tag_starting_hitpoints", 10),
            deafen_window=state.get("tag_deafen_window", 0.2),
            expected_team=state.get("tag_expected_team", 0),
            expected_player=state.get("tag_expected_player", 1),
            warning_pulse_count=state.get("tag_warning_pulse_count", 5),
            warning_pulse_duration=state.get("tag_warning_pulse_duration", 0.6),
            max_ammo=state.get("tag_max_ammo", 10),
            shot_cooldown=state.get("tag_shot_cooldown", 0.3),
            reload_duration=state.get("tag_reload_duration", 3.0),
        )

    def warning_duration(self) -> float:
        """Return the total Starting countdown duration = pulse count x pulse duration."""
        return self.warning_pulse_count * self.warning_pulse_duration


tag_config: StateSlot = StateSlot(_CONFIG_KEY, TagConfig.from_state, TagConfig)
