"""Magnetometer mode: one bar per axis, filled by how strong a field that axis reads.

x shows on the personal strip, y on directional, and z on every global strip.
Each bar takes one colour for a positive reading and another for a negative
one, and fills in proportion up to ``MAG_MAX``.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, Simulation
from engine.state import Scope
from packs.scenes.hardware_test.rules.magnetic_rule import MAG_LOG_INTERVAL, MAG_MAX
from packs.scenes.hardware_test.tests.helpers import (
    ACCELEROMETER,
    BLUE,
    CYAN,
    EVERY_STRIP,
    GLOBAL_STRIPS,
    GREEN,
    IR,
    MAGENTA,
    MAGNETOMETER,
    RED,
    YELLOW,
    all_white,
    press,
)


def test_a_field_outside_magnetometer_mode_draws_no_bars(sim):
    # IR mode idles white on every strip, so any bar would show over it.
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", IR)

    device.magnetize(MAG_MAX, -MAG_MAX, MAG_MAX)
    sim.advance(0.1)

    assert all_white(device)


@pytest.mark.parametrize(
    ("field", "strips", "color"),
    [
        ((MAG_MAX, 0.0, 0.0), [Scope.PERSONAL], RED),
        ((-MAG_MAX, 0.0, 0.0), [Scope.PERSONAL], CYAN),
        ((0.0, MAG_MAX, 0.0), [Scope.DIRECTIONAL], GREEN),
        ((0.0, -MAG_MAX, 0.0), [Scope.DIRECTIONAL], MAGENTA),
        ((0.0, 0.0, MAG_MAX), GLOBAL_STRIPS, BLUE),
        ((0.0, 0.0, -MAG_MAX), GLOBAL_STRIPS, YELLOW),
    ],
    ids=["x+", "x-", "y+", "y-", "z+", "z-"],
)
def test_a_full_field_on_one_axis_fills_its_bar_in_its_signs_colour(sim, field, strips, color):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)

    device.magnetize(*field)
    sim.advance(0.1)

    assert all(device.strip(scope).all_lit(color) for scope in strips)


def test_entering_magnetometer_mode_draws_the_bars_for_the_field_already_there(sim):
    # z negative, not positive: the accelerometer mode before it leaves the
    # global strips blue at rest, so only yellow shows the z bar was drawn.
    device = sim.add_device("red", scene="hardware_test")
    device.magnetize(MAG_MAX, MAG_MAX, -MAG_MAX)

    press(device, "B", MAGNETOMETER)

    assert device.strip(Scope.PERSONAL).all_lit(RED)
    assert device.strip(Scope.DIRECTIONAL).all_lit(GREEN)
    assert all(device.strip(scope).all_lit(YELLOW) for scope in GLOBAL_STRIPS)


def test_a_zero_field_leaves_every_bar_dark(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)

    device.magnetize(0.0, 0.0, 0.0)
    sim.advance(0.1)

    assert all(device.strip(scope).dark for scope in EVERY_STRIP)


def test_a_half_field_fills_half_the_bar(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)

    device.magnetize(MAG_MAX / 2, 0.0, 0.0)
    sim.advance(0.1)

    personal = device.strip(Scope.PERSONAL)
    assert personal.lit == personal.size // 2


def test_a_field_beyond_the_maximum_fills_the_bar_and_no_more(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)

    device.magnetize(2 * MAG_MAX, 0.0, 0.0)
    sim.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(RED)


def test_the_bars_follow_a_changing_field(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)
    device.magnetize(MAG_MAX, 0.0, 0.0)
    sim.advance(0.1)

    device.magnetize(MAG_MAX / 2, 0.0, 0.0)
    sim.advance(0.1)

    personal = device.strip(Scope.PERSONAL)
    assert personal.lit == personal.size // 2


def test_the_bar_takes_the_other_colour_when_the_field_changes_sign(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)
    device.magnetize(MAG_MAX, 0.0, 0.0)
    sim.advance(0.1)

    device.magnetize(-MAG_MAX, 0.0, 0.0)
    sim.advance(0.1)

    assert device.strip(Scope.PERSONAL).all_lit(CYAN)


def test_a_leaves_the_bars_as_they_are_in_magnetometer_mode(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)
    device.magnetize(MAG_MAX / 2, -MAG_MAX, MAG_MAX)
    sim.advance(0.1)
    before = [device.strip(scope).pixels for scope in EVERY_STRIP]

    device.tap("A")

    assert [device.strip(scope).pixels for scope in EVERY_STRIP] == before


def test_a_plays_and_sends_nothing_in_magnetometer_mode(sim):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)

    device.tap("A")

    assert device.played == []
    assert device.buzzed == []
    assert device.ir_sent == []
    assert device.radio_sent == []


def test_the_console_logs_the_field_it_reads(sim, capsys):
    device = sim.add_device("red", scene="hardware_test")
    device.magnetize(1.0, 2.0, 3.0)

    press(device, "B", MAGNETOMETER)

    assert "mag (1.0, 2.0, 3.0)" in capsys.readouterr().out


def just_logged_a_field(sim: Simulation, capsys: pytest.CaptureFixture[str]) -> None:
    """Advance until the console logs a field, and drop everything logged so far."""
    capsys.readouterr()
    sim.run_until(lambda: "mag " in capsys.readouterr().out)


def test_the_console_logs_no_field_again_within_the_log_interval(sim, capsys):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)
    just_logged_a_field(sim, capsys)

    sim.advance(MAG_LOG_INTERVAL - TICK)

    assert "mag " not in capsys.readouterr().out


def test_the_console_logs_the_field_again_once_the_log_interval_has_passed(sim, capsys):
    device = sim.add_device("red", scene="hardware_test")
    press(device, "B", MAGNETOMETER)
    just_logged_a_field(sim, capsys)

    sim.advance(MAG_LOG_INTERVAL + TICK)

    assert capsys.readouterr().out.count("mag ") == 1


def test_no_field_is_logged_outside_magnetometer_mode(sim, capsys):
    # Accelerometer mode logs its own readings, tagged "accel".
    device = sim.add_device("red", scene="hardware_test")
    device.magnetize(1.0, 2.0, 3.0)

    press(device, "B", ACCELEROMETER)
    sim.advance(1.0)

    assert "mag " not in capsys.readouterr().out
