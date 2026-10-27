"""Accelerometer mode: one bar per axis, filled by how hard that axis reads.

x shows on the personal strip, y on directional, and z on every global strip.
Each bar takes one colour for a positive reading and another for a negative
one, and fills in proportion up to ``ACCEL_MAX``.
"""

from __future__ import annotations

import pytest

from engine.state import Scope
from packs.scenes.hardware_test.rules.motion_rule import ACCEL_MAX
from packs.scenes.hardware_test.tests.helpers import (
    ACCELEROMETER,
    BLUE,
    CYAN,
    EVERY_STRIP,
    RED,
    press,
)

GLOBAL_STRIPS = [Scope.Global.MAIN, Scope.Global.BUFF, Scope.Global.DEBUFF]


@pytest.mark.parametrize(
    ("reading", "strips", "color"),
    [
        ((ACCEL_MAX, 0.0, 0.0), [Scope.PERSONAL], RED),
        ((-ACCEL_MAX, 0.0, 0.0), [Scope.PERSONAL], CYAN),
        ((0.0, ACCEL_MAX, 0.0), [Scope.DIRECTIONAL], 0x00FF00),
        ((0.0, -ACCEL_MAX, 0.0), [Scope.DIRECTIONAL], 0xFF00FF),
        ((0.0, 0.0, ACCEL_MAX), GLOBAL_STRIPS, BLUE),
        ((0.0, 0.0, -ACCEL_MAX), GLOBAL_STRIPS, 0xFFFF00),
    ],
    ids=["x+", "x-", "y+", "y-", "z+", "z-"],
)
def test_a_full_reading_on_one_axis_fills_its_bar_in_its_signs_colour(sim, reading, strips, color):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)

    device.accelerate(*reading)
    sim.advance(0.1)

    assert all(device.strip(scope).all_lit(color) for scope in strips)


def test_at_rest_gravity_fills_the_z_bar_and_leaves_x_and_y_dark(sim):
    device = sim.add_device("red", scene="hardware_test")

    press(device, "B", ACCELEROMETER)

    assert all(device.strip(scope).all_lit(BLUE) for scope in GLOBAL_STRIPS)
    assert device.strip(Scope.PERSONAL).dark
    assert device.strip(Scope.DIRECTIONAL).dark


def test_a_zero_reading_leaves_every_bar_dark(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)

    device.accelerate(0.0, 0.0, 0.0)
    sim.advance(0.1)

    assert all(device.strip(scope).dark for scope in EVERY_STRIP)


def test_a_half_reading_fills_half_the_bar(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)

    device.accelerate(ACCEL_MAX / 2, 0.0, 0.0)
    sim.advance(0.1)

    personal = device.strip(Scope.PERSONAL)
    assert personal.lit == personal.size // 2


def test_a_reading_beyond_the_maximum_fills_the_bar_and_no_more(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)

    device.accelerate(2 * ACCEL_MAX, 0.0, 0.0)
    sim.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(RED)


def test_the_bars_follow_a_changing_reading(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)
    device.accelerate(ACCEL_MAX, 0.0, 0.0)
    sim.advance(0.1)

    device.accelerate(ACCEL_MAX / 2, 0.0, 0.0)
    sim.advance(0.1)

    assert device.strip(Scope.PERSONAL).lit == device.strip(Scope.PERSONAL).size // 2


def test_the_bar_takes_the_other_colour_when_the_reading_changes_sign(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)
    device.accelerate(ACCEL_MAX, 0.0, 0.0)
    sim.advance(0.1)

    device.accelerate(-ACCEL_MAX, 0.0, 0.0)
    sim.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(CYAN)


def test_a_leaves_the_bars_as_they_are_in_accelerometer_mode(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)
    device.accelerate(ACCEL_MAX / 2, -ACCEL_MAX, ACCEL_MAX)
    sim.advance(0.1)
    before = [device.strip(scope).pixels for scope in EVERY_STRIP]

    device.tap("A")

    assert [device.strip(scope).pixels for scope in EVERY_STRIP] == before


def test_a_plays_and_sends_nothing_in_accelerometer_mode(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", ACCELEROMETER)

    device.tap("A")

    assert device.played == []
    assert device.buzzed == []
    assert device.ir_sent == []
