from __future__ import annotations

from packs.scenes.hardware_test.rules.helpers.axis_bars import show_axis_bars, start_axis_bars
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.phases import MODE_ACCELEROMETER

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

    from engine.input import InputEvents
    from engine.state import GameState

ACCEL_MAX: Final = 9.8

# Minimum seconds between accelerometer log lines (~2 per second).
ACCEL_LOG_INTERVAL: Final = 0.5


class HwTestMotionRule(HwModeRule):
    def __init__(self) -> None:
        super().__init__(MODE_ACCELEROMETER)

    def on_enter(self, state: GameState) -> None:
        start_axis_bars(state.effect_controls)

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        self._update_axes(event, state)

    def _update_axes(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.acceleration is None:
            return

        acceleration = event.acceleration
        show_axis_bars(state.effect_controls, acceleration, ACCEL_MAX)

        # ``state.total`` is monotonic, so the last-logged timestamp needs no
        # teardown across mode changes.
        if (
            "accel_log_last" not in state
            or state.total - state.get("accel_log_last", 0.0) >= ACCEL_LOG_INTERVAL
        ):
            state.set("accel_log_last", state.total)
            print("accel " + str((acceleration.x, acceleration.y, acceleration.z)))


RULE = HwTestMotionRule()
