"""B steps through the six modes in turn: RGB, Accelerometer, Magnetometer, IR, Radio, SFX.

Each mode is told apart by what it shows, and IR from Radio, which both show
white, by whether A sends IR.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.simulation import TICK, SimulatedDevice
from engine.state import Scope
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.helpers.mode import HW_TEST_PAYLOAD
from packs.scenes.hardware_test.tests.helpers import (
    ACCELEROMETER,
    EVERY_STRIP,
    IR,
    MAGNETOMETER,
    RADIO,
    SFX,
    WHITE,
    enter_mode,
)


def shows_rgb(device: SimulatedDevice) -> bool:
    """Water on personal: lit, in shades of blue."""
    personal = device.strip(Scope.PERSONAL)
    return not personal.dark and personal.shades_of(0x0000FF)


def shows_accelerometer(device: SimulatedDevice) -> bool:
    """At rest, gravity fills the z bar on global main blue and leaves the x bar dark."""
    return device.strip(Scope.Global.MAIN).all_lit(0x0000FF) and device.strip(Scope.PERSONAL).dark


def shows_magnetometer(device: SimulatedDevice) -> bool:
    """Every bar empty."""
    return all(device.strip(scope).dark for scope in EVERY_STRIP)


def sends_ir_on_a(device: SimulatedDevice) -> bool:
    device.forget()
    device.tap("A")
    return bool(device.ir_sent)


def shows_ir(device: SimulatedDevice) -> bool:
    """White everywhere, and A sends IR."""
    return all(device.strip(scope).all_lit(WHITE) for scope in EVERY_STRIP) and sends_ir_on_a(
        device
    )


def shows_radio(device: SimulatedDevice) -> bool:
    """White everywhere, and A sends no IR."""
    return all(device.strip(scope).all_lit(WHITE) for scope in EVERY_STRIP) and not sends_ir_on_a(
        device
    )


def shows_sfx(device: SimulatedDevice) -> bool:
    """Cyan on personal only."""
    others = [scope for scope in EVERY_STRIP if scope is not Scope.PERSONAL]
    return device.strip(Scope.PERSONAL).all_lit(0x00FFFF) and all(
        device.strip(scope).dark for scope in others
    )


@pytest.mark.parametrize(
    ("presses", "shows"),
    [
        (ACCELEROMETER, shows_accelerometer),
        (MAGNETOMETER, shows_magnetometer),
        (IR, shows_ir),
        (RADIO, shows_radio),
        (SFX, shows_sfx),
        (SFX + 1, shows_rgb),
    ],
    ids=["accelerometer", "magnetometer", "ir", "radio", "sfx", "back-to-rgb"],
)
def test_each_press_of_b_steps_one_mode_on(
    sim, presses: int, shows: Callable[[SimulatedDevice], bool]
):
    device = sim.add_device("red", scene="hardware_test")

    enter_mode(device, presses)

    assert shows(device)


def test_a_flash_cut_short_by_a_mode_change_does_not_light_a_later_mode(sim):
    # Two presses of B, from IR to SFX, take less than the flash. SFX leaves
    # the directional strip dark; the IR flash, had it outlived IR mode,
    # would end by lighting it white.
    device = sim.add_device("red", scene="hardware_test")
    enter_mode(device, IR)
    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    enter_mode(device, SFX - IR)
    sim.advance(FLASH_DURATION)

    assert device.strip(Scope.DIRECTIONAL).dark
