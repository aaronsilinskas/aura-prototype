"""The element browser on the Simulation test harness: A pages, B levels.

The first page shows fire on the directional strip; the second shows Time,
whose grey tickers sweep round it, one per level. So the directional strip
alone tells which page is up and, on the second page, at what level.
"""

from __future__ import annotations

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope

SECOND_PAGE = {"page": 1}


def tickers(sim: Simulation, device: SimulatedDevice) -> int:
    """How many of Time's tickers the directional strip shows: the level, on the second page.

    Neither Time's sand nor fire ever shows blue, so a pixel with blue is a
    ticker. A ticker can fall between pixels, so this is the most seen over
    half a second.
    """
    most = 0
    for _ in range(30):
        sim.advance(TICK)
        most = max(most, sum(1 for p in device.strip(Scope.DIRECTIONAL).pixels if p & 0xFF))
    return most


def shows_first_page(sim: Simulation, device: SimulatedDevice) -> bool:
    """Fire on the directional strip: lit, with no ticker."""
    return tickers(sim, device) == 0 and not device.strip(Scope.DIRECTIONAL).dark


def test_on_boot_the_first_page_shows(sim):
    device = sim.add_device("red", scene="element_browser")

    assert shows_first_page(sim, device)


def test_on_boot_the_level_is_1(sim):
    device = sim.add_device("red", scene="element_browser", scene_data=SECOND_PAGE)

    assert tickers(sim, device) == 1


def test_on_boot_the_level_is_the_one_scene_data_sets(sim):
    device = sim.add_device("red", scene="element_browser", scene_data={"page": 1, "level": 4})

    assert tickers(sim, device) == 4


def test_a_advances_to_the_next_page(sim):
    device = sim.add_device("red", scene="element_browser")

    device.tap("A")

    assert tickers(sim, device) == 1


def test_a_keeps_the_level(sim):
    device = sim.add_device("red", scene="element_browser", scene_data={"level": 4})

    device.tap("A")

    assert tickers(sim, device) == 4


def test_a_wraps_from_the_last_page_to_the_first(sim):
    device = sim.add_device("red", scene="element_browser", scene_data=SECOND_PAGE)

    device.tap("A")

    assert shows_first_page(sim, device)


def test_b_raises_the_level_and_keeps_the_page(sim):
    device = sim.add_device("red", scene="element_browser", scene_data=SECOND_PAGE)

    device.tap("B")

    assert tickers(sim, device) == 2


def test_b_keeps_the_first_page(sim):
    device = sim.add_device("red", scene="element_browser")

    device.tap("B")

    assert shows_first_page(sim, device)


def test_b_wraps_the_level_from_10_to_1(sim):
    device = sim.add_device("red", scene="element_browser", scene_data={"page": 1, "level": 10})

    device.tap("B")

    assert tickers(sim, device) == 1


def test_with_no_button_pressed_the_display_stays_as_it_is(sim):
    device = sim.add_device("red", scene="element_browser", scene_data={"page": 1, "level": 3})

    sim.advance(3.0)

    assert tickers(sim, device) == 3
