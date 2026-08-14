from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.input import InputEvents
from engine.state import GameState, Scope
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import HwModeRule
from packs.scenes.hardware_test.rules.helpers.phases import MODE_MAGNETOMETER

# Sensitivity, not a calibrated resting point: raw MagneticData carries a
# per-axis hard-iron/chip offset, so bars are only reliable as a "did it
# move" signal, not an absolute-level one. Chosen so an Earth-field rotation
# produces a visible bar swing and a handheld magnet pegs the bar.
MAG_MAX: Final = 100.0

# Minimum seconds between magnetometer log lines (~2 per second).
MAG_LOG_INTERVAL: Final = 0.5

X_POS_COLOR: Final = 0xFF0000
X_NEG_COLOR: Final = 0x00FFFF
Y_POS_COLOR: Final = 0x00FF00
Y_NEG_COLOR: Final = 0xFF00FF
Z_POS_COLOR: Final = 0x0000FF
Z_NEG_COLOR: Final = 0xFFFF00

_AXIS_MAP: Final = (
    ("x", Scope.PERSONAL, X_POS_COLOR, X_NEG_COLOR),
    ("y", Scope.DIRECTIONAL, Y_POS_COLOR, Y_NEG_COLOR),
    ("z", Scope.Global.ALL, Z_POS_COLOR, Z_NEG_COLOR),
)


class HwTestMagneticRule(HwModeRule):
    """Drives the Magnetometer mode: idle entry effect and per-tick axis bars.

    Maps magnetometer axes to per-scope ``basic.progress`` bars every tick,
    independent of button state. Button A has no behaviour in this mode.
    """

    def __init__(self) -> None:
        super().__init__(MODE_MAGNETOMETER)

    def on_enter(self, state: GameState) -> None:
        ec = state.effect_controls
        ec.set_effect(Scope.PERSONAL, "basic.progress", {"color": 0xFF0000, "progress": 0.0})
        ec.set_effect(Scope.DIRECTIONAL, "basic.progress", {"color": 0x00FF00, "progress": 0.0})
        ec.set_effect(Scope.Global.ALL, "basic.progress", {"color": 0x0000FF, "progress": 0.0})

    def on_input_event(self, event: InputEvents.Sensors, state: GameState) -> None:
        self._update_axes(event, state)

    def _update_axes(self, event: InputEvents.Sensors, state: GameState) -> None:
        if event.magnetic is None:
            return

        ec = state.effect_controls
        magnetic = event.magnetic
        for field, scope, pos_color, neg_color in _AXIS_MAP:
            mag = getattr(magnetic, field)
            color = pos_color if mag >= 0 else neg_color
            progress = min(1.0, abs(mag) / MAG_MAX)
            ec.set_effect(scope, "basic.progress", {"color": color, "progress": progress})

        # Throttle console logging to ~2/sec. ``state.total`` is monotonic, so
        # the last-logged timestamp needs no teardown across mode changes.
        if (
            "mag_log_last" not in state
            or state.total - state.get("mag_log_last", 0.0) >= MAG_LOG_INTERVAL
        ):
            state.set("mag_log_last", state.total)
            print("mag " + str((magnetic.x, magnetic.y, magnetic.z)))


RULE = HwTestMagneticRule()
