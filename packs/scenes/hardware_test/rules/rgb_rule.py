from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import RGB_IDLE
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RGB


class HwTestRgbRule(HwModeRule):
    """Drives the RGB mode: idle entry effect and Button A brightness cycling.

    On entry, sets ``rgb_level`` to 1 and applies the ``RGB_IDLE`` effect table
    at level 1. Button A steps ``rgb_level`` 1 → 10 → 1 and re-applies the
    ``RGB_IDLE`` effect table at the new level.
    """

    def __init__(self) -> None:
        super().__init__(MODE_RGB)

    def on_enter(self, state: GameState) -> None:
        ec = state.effect_controls
        state.set("rgb_level", 1)
        for scope, name in RGB_IDLE:
            ec.set_effect(scope, name, {"level": 1})

    def on_input_event(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        new_level = (state.get("rgb_level", 1) % 10) + 1
        state.set("rgb_level", new_level)
        ec = state.effect_controls
        for scope, name in RGB_IDLE:
            ec.set_effect(scope, name, {"level": new_level})
        print("rgb level -> " + str(new_level))


RULE = HwTestRgbRule()
