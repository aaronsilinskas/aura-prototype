"""B steps through the six modes in turn: RGB, Accelerometer, Magnetometer, IR, Radio, SFX.

Each mode is told apart by what it shows, and IR from Radio, which both show
white, by whether A sends IR.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.simulation import SimulatedDevice
from engine.network import LINE
from engine.state import Scope
from packs.scenes.hardware_test.rules.helpers.hw_mode_rule import FLASH_DURATION
from packs.scenes.hardware_test.rules.magnetic_rule import MAG_MAX
from packs.scenes.hardware_test.tests.helpers import (
    ACCELEROMETER,
    BLUE,
    CYAN,
    GLOBAL_STRIPS,
    IR,
    MAGNETOMETER,
    MODE_COUNT,
    RADIO,
    RED,
    SFX,
    YELLOW,
    all_white,
    every_global_strip_lit,
    press,
    send_on_a,
    strips_but,
)

FIELD = (MAG_MAX, 0.0, -MAG_MAX)
"""The field every device in the cycle reads; only Magnetometer mode shows it.

z is negative, not positive: Accelerometer mode leaves the global strips blue at rest,
so only yellow tells the z bar from it.
"""


def shows_rgb(device: SimulatedDevice) -> bool:
    """Water on personal: lit, in shades of blue."""
    personal = device.strip(Scope.PERSONAL)
    return not personal.dark and personal.shades_of(BLUE)


def shows_accelerometer(device: SimulatedDevice) -> bool:
    """At rest, gravity fills the z bar on global main blue and leaves the x bar dark."""
    return device.strip(Scope.Global.MAIN).all_lit(BLUE) and device.strip(Scope.PERSONAL).dark


def shows_magnetometer(device: SimulatedDevice) -> bool:
    """The bars for ``FIELD``: x full on personal red, z full on every global strip yellow."""
    return device.strip(Scope.PERSONAL).all_lit(RED) and every_global_strip_lit(device, YELLOW)


def sends_ir_on_a(device: SimulatedDevice) -> bool:
    """Tap A; whether it sent IR."""
    device.forget()
    device.tap("A")
    return bool(device.ir_sent)


def shows_white_and_sends_ir_on_a(device: SimulatedDevice) -> bool:
    """IR mode. Taps A."""
    return all_white(device) and sends_ir_on_a(device)


def shows_white_and_sends_no_ir_on_a(device: SimulatedDevice) -> bool:
    """Radio mode. Taps A."""
    return all_white(device) and not sends_ir_on_a(device)


def shows_sfx(device: SimulatedDevice) -> bool:
    """Cyan on personal only."""
    return device.strip(Scope.PERSONAL).all_lit(CYAN) and all(
        device.strip(scope).dark for scope in strips_but(Scope.PERSONAL)
    )


@pytest.mark.parametrize(
    ("mode", "is_in_mode"),
    [
        (ACCELEROMETER, shows_accelerometer),
        (MAGNETOMETER, shows_magnetometer),
        (IR, shows_white_and_sends_ir_on_a),
        (RADIO, shows_white_and_sends_no_ir_on_a),
        (SFX, shows_sfx),
        (MODE_COUNT, shows_rgb),
    ],
    ids=["accelerometer", "magnetometer", "ir", "radio", "sfx", "back-to-rgb"],
)
def test_each_press_of_b_steps_one_mode_on(
    simulation, mode: int, is_in_mode: Callable[[SimulatedDevice], bool]
):
    device = simulation.add_device("red", scene="hardware_test")
    device.magnetize(*FIELD)

    press(device, "B", mode)

    assert is_in_mode(device)


def test_an_ir_flash_cut_short_by_a_mode_change_does_not_light_a_later_mode(simulation):
    # Two presses of B, from IR to SFX, take less than the flash. SFX leaves
    # the directional strip dark; the IR flash, had it outlived IR mode,
    # would end by lighting it white.
    red = simulation.add_device("red", scene="hardware_test")
    blue = simulation.add_device("blue", scene="hardware_test")
    press(red, "B", IR)
    press(blue, "B", IR)
    red.aim(LINE, at=blue)
    send_on_a(simulation, red)

    press(blue, "B", SFX - IR)
    simulation.advance(FLASH_DURATION)

    assert blue.strip(Scope.DIRECTIONAL).dark


def test_a_radio_flash_cut_short_by_a_mode_change_does_not_light_a_later_mode(simulation):
    # One press of B, from Radio to SFX, takes less than the flash. SFX leaves
    # the global strips dark; the radio flash, had it outlived Radio mode,
    # would end by lighting them white.
    red = simulation.add_device("red", scene="hardware_test")
    blue = simulation.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)
    send_on_a(simulation, red)

    press(blue, "B", SFX - RADIO)
    simulation.advance(FLASH_DURATION)

    assert all(blue.strip(scope).dark for scope in GLOBAL_STRIPS)
