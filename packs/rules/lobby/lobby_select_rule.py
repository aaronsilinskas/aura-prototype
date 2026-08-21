"""``LobbySelectRule`` — multi-scope scene picker, config-driven via ``initial_data``.

A lobby scene needs no Python of its own: it declares a ``rule_packs: [["lobby",
"1.0"]]`` entry and seeds ``initial_data`` with a ``lobby`` dict (state key
default-overridable, à la ``FpsLoggerRule``'s ``enabled_key``)::

    "initial_data": {
      "lobby": {
        "scopes": ["personal", "global.main", "directional"],
        "entries": [
          {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
          ...
        ]
      }
    }

``scopes`` is an ordered list of display Scopes ``[S0, S1, ..., Sk]``;
``entries`` is an ordered list of ``{scene, effect, options}`` selectable
scenes (``options`` is passed straight through to ``set_effect`` -- ``level``
is just one of its keys, nothing special). With the current selection at
index ``i`` and ``N`` entries, scope ``Sj`` always previews ``entries[(i +
j) % N]``, so ``S0`` shows the scene Button B would launch right now and the
rest look ahead, wrapping. Button A advances the selection and repaints every
scope; Button B reboots into the current selection via
``state.scene_controls.reboot_into``.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState
from packs.rules.lobby.helpers.lobby_config import LobbyConfig

_DEFAULT_CONFIG_KEY = "lobby"


class LobbySelectRule(GameRule):
    """Cycles a scene selection across a wrapping look-ahead window of scopes.

    Reads its scopes/entries config from a scene's ``initial_data`` under
    *config_key* (default ``"lobby"``); the config is validated and each
    scope string resolved to a ``ScopeValue`` on first read (see
    ``LobbyConfig.from_state``), so an empty or malformed config raises
    there rather than at construction time (this rule is built with no
    ``GameState`` available yet -- see the pack's ``RULE`` singleton below).
    Selection state (the current index, the resolved config) lives entirely
    in ``GameState``; this rule holds no game data of its own, only the
    construction-time key names.
    """

    __slots__ = ("_config_key", "_config_state_key", "_index_key")

    def __init__(self, config_key: str = _DEFAULT_CONFIG_KEY) -> None:
        self._config_key = config_key
        self._config_state_key = config_key + "_resolved"
        self._index_key = config_key + "_index"
        self.on(InputEvents.Sensors, self._handle)

    def _config(self, state: GameState) -> LobbyConfig:
        """Return the resolved config, building and caching it in *state* on first use."""
        if not state.has(self._config_state_key):
            state.set(self._config_state_key, LobbyConfig.from_state(state, self._config_key))
        return state.get_or_none(self._config_state_key, LobbyConfig)  # type: ignore[return-value]

    def _paint(self, config: LobbyConfig, index: int, state: GameState) -> None:
        """Call ``set_effect`` once per scope, in order, for the look-ahead window at *index*."""
        count = len(config.entries)
        for offset, scope in enumerate(config.scopes):
            entry = config.entries[(index + offset) % count]
            state.effect_controls.set_effect(scope, entry.effect, entry.options)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        config = self._config(state)

        if not state.has(self._index_key):
            state.set(self._index_key, 0)
            self._paint(config, 0, state)
            return

        index = state.get(self._index_key, 0)

        if event.buttons.is_pressed("A"):
            index = (index + 1) % len(config.entries)
            state.set(self._index_key, index)
            self._paint(config, index, state)
        elif event.buttons.is_pressed("B"):
            state.scene_controls.reboot_into(config.entries[index].scene)


RULE = LobbySelectRule()
