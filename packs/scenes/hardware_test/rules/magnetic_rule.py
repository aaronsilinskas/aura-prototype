from __future__ import annotations

from packs.scenes.hardware_test.rules.helpers.axis_bars import show_axis_bars, start_axis_bars
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.phases import MODE_MAGNETOMETER

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final

    from engine.input import InputEvents
    from engine.state import GameState

# Sensitivity, not a calibrated resting point: raw MagneticData carries a
# per-axis hard-iron/chip offset, so bars are only reliable as a "did it
# move" signal, not an absolute-level one. Chosen so an Earth-field rotation
# produces a visible bar swing and a handheld magnet pegs the bar.
MAG_MAX: Final = 100.0

# Minimum seconds between magnetometer log lines (~2 per second).
MAG_LOG_INTERVAL: Final = 0.5


class HwTestMagneticRule(HwModeRule):
    def __init__(self) -> None:
        super().__init__(MODE_MAGNETOMETER)

    def on_enter(self, state: GameState) -> None:
        start_axis_bars(state.effect_controls)

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        self._update_axes(event, state)

    def _update_axes(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.magnetic is None:
            return

        magnetic = event.magnetic
        show_axis_bars(state.effect_controls, magnetic, MAG_MAX)

        # ``state.total`` is monotonic, so the last-logged timestamp needs no
        # teardown across mode changes.
        if (
            "mag_log_last" not in state
            or state.total - state.get("mag_log_last", 0.0) >= MAG_LOG_INTERVAL
        ):
            state.set("mag_log_last", state.total)
            print("mag " + str((magnetic.x, magnetic.y, magnetic.z)))


RULE = HwTestMagneticRule()
