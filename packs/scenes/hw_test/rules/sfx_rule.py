from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.hw_test.rules.helpers.mode import MODE_SFX, current_mode


class HwTestSfxRule(GameRule):
    """Fires the ``scene.sfx_test`` cue on Button A in SFX mode.

    Button A plays the test sound/haptic cue on ``Scope.PERSONAL``. Presses in
    any other mode are ignored.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if current_mode(state) != MODE_SFX:
            return
        if not event.buttons.is_pressed("A"):
            return

        state.effect_controls.set_effect(Scope.PERSONAL, "scene.sfx_test", {})
        print("playing sfx")


RULE = HwTestSfxRule()
