"""Shared moves and reads for the hardware_test simulation tests."""

from __future__ import annotations

from app.simulation import SimulatedDevice
from engine.state import Scope, ScopeValue

BLUE = 0x0000FF
CYAN = 0x00FFFF
GREEN = 0x00FF00
RED = 0xFF0000
WHITE = 0xFFFFFF

EVERY_STRIP = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
]

GLOBAL_STRIPS = [Scope.Global.MAIN, Scope.Global.BUFF, Scope.Global.DEBUFF]

RGB, ACCELEROMETER, MAGNETOMETER, IR, RADIO, SFX = range(6)
"""Each mode's place in the cycle: how many presses of B reach it from RGB, where a device
switches on."""

MODE_COUNT = 6
"""Presses of B that go once round the cycle, back to where they started."""


def press(device: SimulatedDevice, button: str, times: int) -> None:
    for _ in range(times):
        device.tap(button)


def strips_but(scope: ScopeValue) -> list[ScopeValue]:
    return [other for other in EVERY_STRIP if other is not scope]


def all_white(device: SimulatedDevice) -> bool:
    return all(device.strip(scope).all_lit(WHITE) for scope in EVERY_STRIP)
