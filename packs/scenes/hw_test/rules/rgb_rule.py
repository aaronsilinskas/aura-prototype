from __future__ import annotations

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState
from packs.scenes.hw_test.rules.helpers.mode import _RGB_IDLE, MODE_RGB, current_mode


class HwTestRgbRule(GameRule):
    """Cycles the RGB idle brightness level on Button A in RGB mode.

    Button A steps ``rgb_level`` 1 → 10 → 1 and re-applies the ``_RGB_IDLE``
    effect table at the new level. Presses in any other mode are ignored.
    """

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if current_mode(state) != MODE_RGB:
            return
        if not event.buttons.is_pressed("A"):
            return

        new_level = (state.get("rgb_level", 1) % 10) + 1
        state.set("rgb_level", new_level)
        ec = state.effect_controls
        for scope, name in _RGB_IDLE:
            ec.set_effect(scope, name, {"level": new_level})
        print("rgb level -> " + str(new_level))


RULE = HwTestRgbRule()
