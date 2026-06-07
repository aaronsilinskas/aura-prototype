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
    ("x", Scope.PERSONAL, X_POS_COLOR, X_NEG_COLOR, "hw_motion_receipt_x", "hw_motion_color_x"),
    ("y", Scope.DIRECTIONAL, Y_POS_COLOR, Y_NEG_COLOR, "hw_motion_receipt_y", "hw_motion_color_y"),
    ("z", Scope.Global.ALL, Z_POS_COLOR, Z_NEG_COLOR, "hw_motion_receipt_z", "hw_motion_color_z"),
)


class HwTestMotionRule(GameRule):
    """Maps accelerometer axes to brightness and colours per scope."""

    def __init__(self) -> None:
        self.on(InputEvents.ButtonAndAcceleration, self._handle)

    def _handle(self, event: InputEvents.ButtonAndAcceleration, state: GameState) -> None:
        if state.get("hw_mode", -1) != 1:
            return

        if event.acceleration is None:
            return

        ec = state.effect_controls
        acceleration = event.acceleration
        for field, scope, pos_color, neg_color, receipt_key, color_key in _AXIS_MAP:
            accel = getattr(acceleration, field)
            color = pos_color if accel >= 0 else neg_color
            brightness = min(1.0, abs(accel) / ACCEL_MAX)

            stored_receipt = state.get(receipt_key, None)
            stored_color = state.get(color_key, None)

            if (
                stored_receipt is not None
                and not stored_receipt.is_stopped()
                and stored_color == color
            ):
                stored_receipt.brightness = brightness
            else:
                receipt = ec.set_effect(scope, "basic.solid", {"color": color})
                receipt.brightness = brightness
                state.set(receipt_key, receipt)
                state.set(color_key, color)


RULE = HwTestMotionRule()
