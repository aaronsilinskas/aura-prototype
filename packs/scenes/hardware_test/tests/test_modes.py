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
    BLUE,
    CYAN,
    EVERY_STRIP,
    GLOBAL_STRIPS,
    IR,
    MAGNETOMETER,
    MODE_COUNT,
    RADIO,
    SFX,
    all_white,
    press,
    send_a_packet,
    strips_but,
)


def shows_rgb(device: SimulatedDevice) -> bool:
    """Water on personal: lit, in shades of blue."""
    personal = device.strip(Scope.PERSONAL)
    return not personal.dark and personal.shades_of(BLUE)


def shows_accelerometer(device: SimulatedDevice) -> bool:
    """At rest, gravity fills the z bar on global main blue and leaves the x bar dark."""
    return device.strip(Scope.Global.MAIN).all_lit(BLUE) and device.strip(Scope.PERSONAL).dark


def shows_magnetometer(device: SimulatedDevice) -> bool:
    """Every bar empty."""
    return all(device.strip(scope).dark for scope in EVERY_STRIP)


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
    sim, mode: int, is_in_mode: Callable[[SimulatedDevice], bool]
):
    device = sim.add_device("red", scene="hardware_test")

    press(device, "B", mode)

    assert is_in_mode(device)


def test_an_ir_flash_cut_short_by_a_mode_change_does_not_light_a_later_mode(sim):
    # Two presses of B, from IR to SFX, take less than the flash. SFX leaves
    # the directional strip dark; the IR flash, had it outlived IR mode,
    # would end by lighting it white.
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", IR)
    device.receive_ir(HW_TEST_PAYLOAD)
    sim.advance(TICK)

    press(device, "B", SFX - IR)
    sim.advance(FLASH_DURATION)

    assert device.strip(Scope.DIRECTIONAL).dark


def test_a_radio_flash_cut_short_by_a_mode_change_does_not_light_a_later_mode(sim):
    # One press of B, from Radio to SFX, takes less than the flash. SFX leaves
    # the global strips dark; the radio flash, had it outlived Radio mode,
    # would end by lighting them white.
    red = sim.add_device("red", scene="hardware_test")
    blue = sim.add_device("blue", scene="hardware_test")
    press(red, "B", RADIO)
    press(blue, "B", RADIO)
    send_a_packet(sim, red)

    press(blue, "B", SFX - RADIO)
    sim.advance(FLASH_DURATION)

    assert all(blue.strip(scope).dark for scope in GLOBAL_STRIPS)
