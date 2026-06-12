from __future__ import annotations

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.phases import MODE_SFX


class HwTestSfxRule(HwModeRule):
    """Drives the SFX mode: cyan idle entry effect and Button A test cue.

    On entry, shows a cyan solid on ``Scope.PERSONAL``. Button A plays the
    test sound/haptic cue on ``Scope.PERSONAL``.
    """

    def __init__(self) -> None:
        super().__init__(MODE_SFX)

    def on_enter(self, state: GameState) -> None:
        state.effect_controls.set_effect(Scope.PERSONAL, "basic.solid", {"color": 0x00FFFF})

    def on_input_event(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if not event.buttons.is_pressed("A"):
            return

        state.effect_controls.set_effect(Scope.PERSONAL, "scene.sfx_test", {})
        print("playing sfx")


RULE = HwTestSfxRule()
