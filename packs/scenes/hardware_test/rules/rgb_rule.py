from __future__ import annotations

from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.mode import RGB_IDLE
from packs.scenes.hardware_test.rules.helpers.phases import MODE_RGB

TYPE_CHECKING = False

if TYPE_CHECKING:
    from engine.input import InputEvents
    from engine.state import GameState


class HwTestRgbRule(HwModeRule):
    def __init__(self) -> None:
        super().__init__(MODE_RGB)

    def on_enter(self, state: GameState) -> None:
        ec = state.effect_controls
        state.set("rgb_level", 1)
        for scope, name in RGB_IDLE:
            ec.set_effect(scope, name, {"level": 1})

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        new_level = (state.get("rgb_level", 1) % 10) + 1
        state.set("rgb_level", new_level)
        ec = state.effect_controls
        for scope, name in RGB_IDLE:
            ec.set_effect(scope, name, {"level": new_level})
        print("rgb level -> " + str(new_level))


RULE = HwTestRgbRule()
