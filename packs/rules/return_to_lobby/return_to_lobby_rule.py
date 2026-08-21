"""``ReturnToLobbyRule`` -- shared return-to-lobby pack.

Ships as its own pack (``packs/rules/return_to_lobby/``), separate from
``lobby/``, because the rule-pack loader includes *every* item in an
included pack: a game scene must be able to include just the return rule
without also pulling in whatever else the lobby pack ships.
"""

from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

_HELD_KEY: Final = "return_to_lobby_held"
_CONFIG_KEY: Final = "return_to_lobby"
_DEFAULT_HOLD_SECONDS: Final = 5.0


class ReturnToLobbyRule(GameRule):
    """Reboots back to the launching scene after both buttons are held.

    Accumulates both-buttons-held elapsed time in ``GameState`` -- the rule
    itself is game-data-stateless -- resetting to zero the instant either
    button releases. Reaching the ``hold_seconds`` threshold (read from a
    scene's ``initial_data["return_to_lobby"]["hold_seconds"]``, default
    5.0) calls ``state.scene_controls.reboot_to_previous()``, rebooting back
    to whichever scene launched the current one. No visual feedback in v1.
    """

    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        buttons = event.buttons
        if not (buttons.is_down("A") and buttons.is_down("B")):
            state.set(_HELD_KEY, 0.0)
            return

        held = state.get(_HELD_KEY, 0.0) + state.elapsed
        hold_seconds = state.get(_CONFIG_KEY, {}).get("hold_seconds", _DEFAULT_HOLD_SECONDS)
        if held >= hold_seconds:
            state.set(_HELD_KEY, 0.0)
            state.scene_controls.reboot_to_previous()
        else:
            state.set(_HELD_KEY, held)


RULE = ReturnToLobbyRule()
