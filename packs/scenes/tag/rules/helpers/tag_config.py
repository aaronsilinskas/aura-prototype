"""``TagConfig`` — the Tag scene's Scene Config.

Holds the scene's Settings, declared in its ``scene.json``, and the values
derived from them. ``TagConfig.__init__`` takes already-resolved values so it
is unit-testable directly; ``from_settings`` builds one from the Settings view.

``tag_config`` is a :class:`engine.state.StateSlot` callable accessor: it lazily
builds the config from ``state.settings`` on first use and caches it under a
single ``GameState`` key.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.settings import Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "tag_config"

NAMESPACE: Final = "scene"


class TagConfig:
    """Immutable tunable configuration for the Tag scene.

    All values are already-resolved, so this can be constructed directly in
    tests. Use :meth:`from_settings` to build one from the scene's Settings.
    """

    __slots__ = (
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
        expected_team: int,
        expected_player: int,
        warning_pulse_count: int,
        warning_pulse_duration: float,
        max_ammo: int,
        shot_cooldown: float,
        reload_duration: float,
    ) -> None:
        self.starting_hitpoints = starting_hitpoints
        self.expected_team = expected_team
        self.expected_player = expected_player
        self.warning_pulse_count = warning_pulse_count
        self.warning_pulse_duration = warning_pulse_duration
        self.max_ammo = max_ammo
        self.shot_cooldown = shot_cooldown
        self.reload_duration = reload_duration

    @classmethod
    def from_settings(cls, settings: Settings) -> TagConfig:
        """Build a config from the scene's Settings, each named as its field."""
        return cls(
            starting_hitpoints=settings.get_int(NAMESPACE, "starting_hitpoints"),
            expected_team=settings.get_int(NAMESPACE, "expected_team"),
            expected_player=settings.get_int(NAMESPACE, "expected_player"),
            warning_pulse_count=settings.get_int(NAMESPACE, "warning_pulse_count"),
            warning_pulse_duration=settings.get_float(NAMESPACE, "warning_pulse_duration"),
            max_ammo=settings.get_int(NAMESPACE, "max_ammo"),
            shot_cooldown=settings.get_float(NAMESPACE, "shot_cooldown"),
            reload_duration=settings.get_float(NAMESPACE, "reload_duration"),
        )

    def warning_duration(self) -> float:
        """Return the total Starting countdown duration = pulse count x pulse duration."""
        return self.warning_pulse_count * self.warning_pulse_duration


def _from_state(state: GameState) -> TagConfig:
    return TagConfig.from_settings(state.settings)


tag_config: StateSlot = StateSlot(_CONFIG_KEY, _from_state, TagConfig)
