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

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

NAMESPACE: Final = "return_to_lobby"
_HELD_KEY: Final = "return_to_lobby_held"


class ReturnToLobbyRule(GameRule):
    """Reboots back to the launching scene once both buttons are held for the
    pack's ``hold_seconds`` Setting.

    The held time lives in ``GameState``; the rule itself is game-data-stateless.
    """

    def __init__(self) -> None:
        self.on(InputEvents.Sensors, self._handle)

    def _handle(self, event: InputEvents.Sensors, state: GameState) -> None:
        buttons = event.buttons
        if not (buttons.is_down("A") and buttons.is_down("B")):
            state.set(_HELD_KEY, 0.0)
            return

        held = state.get(_HELD_KEY, 0.0) + state.elapsed
        if held >= state.settings.get_float(NAMESPACE, "hold_seconds"):
            state.set(_HELD_KEY, 0.0)
            state.scene_controls.reboot_to_previous()
        else:
            state.set(_HELD_KEY, held)


RULE = ReturnToLobbyRule()
