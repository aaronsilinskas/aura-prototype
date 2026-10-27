"""Shared moves and reads for the hardware_test simulation tests."""

from __future__ import annotations

from app.simulation import SimulatedDevice
from engine.state import Scope

GREEN = 0x00FF00
WHITE = 0xFFFFFF

EVERY_STRIP = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
]

ACCELEROMETER, MAGNETOMETER, IR, RADIO, SFX = 1, 2, 3, 4, 5
"""How many B presses from RGB, where a device switches on, reach each mode."""


def enter_mode(device: SimulatedDevice, presses: int) -> None:
    """Press B *presses* times, stepping that many modes on from where the device is."""
    for _ in range(presses):
        device.tap("B")
