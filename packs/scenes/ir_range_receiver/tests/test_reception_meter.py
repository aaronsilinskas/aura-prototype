"""The IR range receiver's reception meter, played on a simulated device.

Shots land through ``receive_ir`` and the real IR stack, each carrying its
sequence number in byte 0 as the transmitter sends it. Every assertion reads
what the device's strips show. A test that depends on a tunable pins it with
``scene_data`` rather than restating the scene's default.
"""

from __future__ import annotations

import math

from app.simulation import SimulatedDevice, Simulation, Strip
from engine.state import Scope

RED = 0xFF0000
GREEN = 0x00FF00

METER_STRIPS = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
]
"""Every strip but ambient: where the meter shows."""

SILENCE_TIMEOUT = 0.5

METER = {
    "ir_range_window_seconds": 1.0,
    "ir_range_silence_timeout": SILENCE_TIMEOUT,
    "ir_range_green_threshold": 1.0,
}
"""A one-second window that goes quiet after ``SILENCE_TIMEOUT``, green only when nothing drops."""

SHOT_SPACING = 0.1
"""Sim seconds between landed shots: well inside ``SILENCE_TIMEOUT``."""


def land(simulation: Simulation, receiver: SimulatedDevice, *sequences: int) -> None:
    """Land one shot per sequence number, ``SHOT_SPACING`` apart."""
    for sequence in sequences:
        receiver.receive_ir(bytes([sequence]))
        simulation.advance(SHOT_SPACING)


def yellow_bar_at(strip: Strip, fraction: float) -> bool:
    """Lit in shades of yellow to *fraction* of the strip, its last pixel dimmed for the edge."""
    yellow = all(p >> 16 == (p >> 8) & 0xFF and p & 0xFF == 0 for p in strip.pixels if p != 0)
    return yellow and strip.lit == math.ceil(fraction * strip.size)


def meter_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("[ir_range")]


def test_a_device_that_has_heard_nothing_shows_solid_red(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    simulation.advance(SHOT_SPACING)

    assert receiver.strip(Scope.PERSONAL).all_lit(RED)


def test_an_unbroken_run_of_shots_shows_solid_green(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    land(simulation, receiver, 0, 1, 2)

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)


def test_the_meter_shows_on_every_strip_but_ambient(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    land(simulation, receiver, 0, 1, 2)

    assert all(receiver.strip(scope).all_lit(GREEN) for scope in METER_STRIPS)
    assert receiver.strip(Scope.AMBIENT).dark


def test_dropped_shots_show_a_yellow_bar_at_the_share_that_arrived(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    land(simulation, receiver, 0, 5)  # 1 to 4 dropped: 2 of 6 arrived

    assert yellow_bar_at(receiver.strip(Scope.PERSONAL), 2 / 6)


def test_the_bar_grows_as_shots_arrive_unbroken_again(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    land(simulation, receiver, 0, 5)  # 2 of 6 arrived

    land(simulation, receiver, 6)  # 3 of 7 arrived

    assert yellow_bar_at(receiver.strip(Scope.PERSONAL), 3 / 7)


def test_dropped_shots_age_out_of_the_window_back_to_green(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    land(simulation, receiver, 0, 5)

    land(simulation, receiver, *range(6, 20))  # 1.4 s of unbroken shots: the gap leaves the window

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)


def test_silence_past_the_timeout_returns_to_solid_red(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    land(simulation, receiver, 0, 1, 2)

    simulation.advance(SILENCE_TIMEOUT + SHOT_SPACING)

    assert receiver.strip(Scope.PERSONAL).all_lit(RED)


def test_a_short_pause_inside_the_timeout_stays_green(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    land(simulation, receiver, 0, 1, 2)

    simulation.advance(SILENCE_TIMEOUT - 2 * SHOT_SPACING)

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)


def test_the_sequence_number_wraps_from_255_without_reading_as_a_drop(simulation):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)

    land(simulation, receiver, 254, 255, 0, 1)

    assert receiver.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_serial_line_reports_the_state_and_drops_once_a_second(simulation, capsys):
    receiver = simulation.add_device("rx", scene="ir_range_receiver", scene_data=METER)
    land(simulation, receiver, 0, 1)  # the boot line prints on the first tick, before any shot
    capsys.readouterr()

    land(simulation, receiver, *range(2, 12))  # a second of unbroken shots

    (line,) = meter_lines(capsys.readouterr().out)
    assert "state=perfect" in line
    assert "dropped=0" in line
