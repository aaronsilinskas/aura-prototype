"""Shared moves and reads for the hardware_test simulation tests."""

from __future__ import annotations

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope, ScopeValue

BLUE = 0x0000FF
CYAN = 0x00FFFF
GREEN = 0x00FF00
MAGENTA = 0xFF00FF
RED = 0xFF0000
WHITE = 0xFFFFFF
YELLOW = 0xFFFF00

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


def strips_but(*scopes: ScopeValue) -> list[ScopeValue]:
    return [other for other in EVERY_STRIP if other not in scopes]


def all_white(device: SimulatedDevice) -> bool:
    return all(device.strip(scope).all_lit(WHITE) for scope in EVERY_STRIP)


def every_global_strip_lit(device: SimulatedDevice, color: int) -> bool:
    return all(device.strip(scope).all_lit(color) for scope in GLOBAL_STRIPS)


def send_a_packet(sim: Simulation, device: SimulatedDevice) -> None:
    """Press A in Radio mode, and advance one tick so the packet lands on every other device.

    A is held, not tapped, so a flash it starts is exactly one tick old on return; a tap
    would also wait out the release.
    """
    device.hold("A")
    sim.advance(TICK)
