from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.engine import GameRule
from engine.input import InputEvents
from engine.state import GameState, Scope

ACCEL_MAX: Final = 9.8

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


class HwTestMotionRule(GameRule):
    """Maps accelerometer axes to per-scope ``basic.progress`` bars."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if state.get("hw_mode", -1) != 1:
            return

        if event.acceleration is None:
            return

        ec = state.effect_controls
        acceleration = event.acceleration
        for field, scope, pos_color, neg_color in _AXIS_MAP:
            accel = getattr(acceleration, field)
            color = pos_color if accel >= 0 else neg_color
            progress = min(1.0, abs(accel) / ACCEL_MAX)
            ec.set_effect(scope, "basic.progress", {"color": color, "progress": progress})


RULE = HwTestMotionRule()
