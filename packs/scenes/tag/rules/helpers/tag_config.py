"""``TagConfig`` — the Tag scene's Scene Config.

Holds the scene's Settings, declared in its ``scene.json``, and the values
derived from them.

``tag_config`` is a :class:`engine.state.StateSlot` callable accessor: it lazily
builds the config from ``state.settings`` on first use and caches it under a
single ``GameState`` key.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.settings import SCENE_NAMESPACE, Settings
from engine.state import GameState, StateSlot

_CONFIG_KEY: Final = "tag_config"


class TagConfig:
    """Immutable configuration for the Tag scene, each field read from the
    scene Setting of the same name."""

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

    def __init__(self, settings: Settings) -> None:
        self.starting_hitpoints = settings.get_int(SCENE_NAMESPACE, "starting_hitpoints")
        self.expected_team = settings.get_int(SCENE_NAMESPACE, "expected_team")
        self.expected_player = settings.get_int(SCENE_NAMESPACE, "expected_player")
        self.warning_pulse_count = settings.get_int(SCENE_NAMESPACE, "warning_pulse_count")
        self.warning_pulse_duration = settings.get_float(SCENE_NAMESPACE, "warning_pulse_duration")
        self.max_ammo = settings.get_int(SCENE_NAMESPACE, "max_ammo")
        self.shot_cooldown = settings.get_float(SCENE_NAMESPACE, "shot_cooldown")
        self.reload_duration = settings.get_float(SCENE_NAMESPACE, "reload_duration")

    def warning_duration(self) -> float:
        """Return the total Starting countdown duration = pulse count x pulse duration."""
        return self.warning_pulse_count * self.warning_pulse_duration


def _from_state(state: GameState) -> TagConfig:
    return TagConfig(state.settings)


tag_config = StateSlot(_CONFIG_KEY, _from_state, TagConfig)
