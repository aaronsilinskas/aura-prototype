"""The event logger on the Simulation test harness, through the element browser.

The element browser loads the ``debug`` pack, so its logger runs on every
event, but logs nothing until ``event_logging_enabled`` is set.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK

LOGGING_ON = {"event_logging_enabled": True}


def logged(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """The ``[debug]`` lines printed since the last read."""
    return [line for line in capsys.readouterr().out.splitlines() if line.startswith("[debug]")]


def logged_input(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """The ``[debug]`` lines for input events printed since the last read."""
    return [line for line in logged(capsys) if " IN:SENSORS " in line]


def test_nothing_is_logged_by_default(simulation, capsys):
    simulation.add_device("red", scene="element_browser")

    simulation.advance(10 * TICK)

    assert logged(capsys) == []


def test_each_input_event_logs_one_line(simulation, capsys):
    simulation.add_device("red", scene="element_browser", scene_data=LOGGING_ON)
    capsys.readouterr()

    simulation.advance(10 * TICK)

    assert len(logged_input(capsys)) == 10


def test_the_line_shows_the_button_states(simulation, capsys):
    device = simulation.add_device("red", scene="element_browser", scene_data=LOGGING_ON)
    device.hold("A")
    capsys.readouterr()

    simulation.advance(TICK)

    assert "buttons=ButtonData(A=DOWN, B=UP)" in logged_input(capsys)[-1]


def test_the_line_shows_the_acceleration(simulation, capsys):
    device = simulation.add_device("red", scene="element_browser", scene_data=LOGGING_ON)
    device.accelerate(1.0, 2.0, 3.0)
    capsys.readouterr()

    simulation.advance(TICK)

    assert "AccelerationData(x=1.0, y=2.0, z=3.0)" in logged_input(capsys)[-1]


def test_the_line_shows_the_time_the_scene_has_run(simulation, capsys):
    simulation.add_device("red", scene="element_browser", scene_data=LOGGING_ON)
    simulation.advance(1.0 - TICK)
    capsys.readouterr()

    simulation.advance(TICK)

    assert logged_input(capsys)[-1].startswith("[debug] t=1.000 ")
