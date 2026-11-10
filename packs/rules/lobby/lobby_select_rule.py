"""``LobbySelectRule`` — multi-scope scene picker, configured by the ``lobby`` pack's Settings.

A lobby scene needs no Python of its own: it declares the ``lobby`` rule pack
and sets the pack's two required Settings in that pack reference::

    "rule_packs": [{
      "name": "lobby", "version": "2.0",
      "settings": {
        "scopes": ["personal", "global.main", "directional"],
        "entries": [
          {"scene": "hardware_test", "effect": "elements.fire", "options": {"level": 5}},
          ...
        ]
      }
    }]

``scopes`` is an ordered list of display Scopes ``[S0, S1, ..., Sk]``;
``entries`` is an ordered list of ``{scene, effect, options}`` selectable
scenes (``options`` is passed straight through to ``set_effect`` -- ``level``
is just one of its keys, nothing special). Entries whose scene this device
can't run (``state.scene_controls.can_run``) are left out, so ``N`` counts
only the playable ones. With the current selection at index ``i`` and ``N``
entries, scope ``Sj`` always previews ``entries[(i +
j) % N]``, so ``S0`` shows the scene Button B would launch right now and the
rest look ahead, wrapping. Button A advances the selection and repaints every
scope; Button B reboots into the current selection via
``state.scene_controls.reboot_into``.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, StateSlot
from packs.rules.lobby.helpers.lobby_config import LobbyConfig

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

_INDEX_KEY: Final = "lobby_index"

_config = StateSlot(
    "lobby_resolved",
    lambda state: LobbyConfig.from_settings(state.settings, state.scene_controls.can_run),
    LobbyConfig,
)


class LobbySelectRule(GameRule):
    """Cycles a scene selection across a wrapping look-ahead window of scopes.

    Reads its scopes/entries config from the pack's Settings via a
    :class:`engine.state.StateSlot`, which resolves and caches a
    ``LobbyConfig`` in ``GameState`` on first read (see
    ``LobbyConfig.from_settings``), so an empty or malformed
    config raises there rather than at construction time (this rule is built
    with no ``GameState`` available yet -- see the pack's ``RULE`` singleton
    below).
    Selection state (the current index, the resolved config) lives entirely
    in ``GameState``; this rule holds no game data of its own.
    """

    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _paint(self, config: LobbyConfig, index: int, state: GameState) -> None:
        """Call ``set_effect`` once per scope, in order, for the look-ahead window at *index*."""
        count = len(config.entries)
        for offset, scope in enumerate(config.scopes):
            entry = config.entries[(index + offset) % count]
            state.effect_controls.set_effect(scope, entry.effect, entry.options)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        config = _config(state)

        if not state.has(_INDEX_KEY):
            state.set(_INDEX_KEY, 0)
            self._paint(config, 0, state)
            return

        index = state.get(_INDEX_KEY, 0)

        if event.buttons.is_pressed("A"):
            index = (index + 1) % len(config.entries)
            state.set(_INDEX_KEY, index)
            self._paint(config, index, state)
        elif event.buttons.is_pressed("B"):
            state.scene_controls.reboot_into(config.entries[index].scene)


RULE = LobbySelectRule()
