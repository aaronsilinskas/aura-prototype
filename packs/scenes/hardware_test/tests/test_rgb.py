"""RGB mode, where a device switches on: five element effects, and A steps their level.

Water shows on personal, fire on directional, lightning on global main, earth
on global buff and ice on global debuff. A steps the level 1 to 10 and back
to 1. Every element burns brighter at level 10 than at level 1, all five
together about twice as bright, so brightness over a watch tells them apart.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope, ScopeValue
from packs.scenes.hardware_test.tests.helpers import BLUE, MODE_COUNT, press

ELEMENT_STRIPS = [
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.Global.MAIN,
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
]
WATCH = 2.0
"""Long enough for level-1 lightning, hidden for up to 1.5 seconds, to strike."""

BRIGHTER = 1.5
"""How many times brighter than level 1 all five strips must burn to count as the top level.

They burn about twice as bright at level 10."""

STRIP_BRIGHTER = 1.15
"""As ``BRIGHTER``, for one strip alone: earth, the least changed, burns about 1.25-1.55x."""


def brightness(
    sim: Simulation, device: SimulatedDevice, strips: list[ScopeValue] = ELEMENT_STRIPS
) -> int:
    """Watch for ``WATCH``; return the summed channels *strips* showed over it."""
    total = 0
    for _ in range(round(WATCH / TICK)):
        sim.advance(TICK)
        for scope in strips:
            for pixel in device.strip(scope).pixels:
                total += (pixel >> 16) + ((pixel >> 8) & 0xFF) + (pixel & 0xFF)
    return total


def test_on_switch_on_the_personal_strip_shows_water_in_shades_of_blue(sim):
    device = sim.add_device("red", scene="hardware_test")

    sim.advance(0.5)

    personal = device.strip(Scope.PERSONAL)
    assert not personal.dark and personal.shades_of(BLUE)


@pytest.mark.parametrize("scope", ELEMENT_STRIPS, ids=lambda scope: scope.keys[0])
def test_on_switch_on_every_element_strip_lights(sim, scope):
    # Lightning strikes now and then, so a strip only has to light at some point.
    device = sim.add_device("red", scene="hardware_test")

    assert brightness(sim, device, [scope]) > 0


def test_on_switch_on_the_ambient_strip_stays_dark(sim):
    device = sim.add_device("red", scene="hardware_test")

    assert brightness(sim, device, [Scope.AMBIENT]) == 0


@pytest.mark.parametrize("scope", ELEMENT_STRIPS, ids=lambda scope: scope.keys[0])
def test_nine_presses_of_a_reach_the_top_level_where_every_element_burns_brighter(sim, scope):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device, [scope])

    press(device, "A", 9)

    assert brightness(sim, device, [scope]) > STRIP_BRIGHTER * at_level_1


def test_a_tenth_press_wraps_the_level_back_to_1(sim):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device)

    press(device, "A", 10)

    assert brightness(sim, device) < BRIGHTER * at_level_1


def test_coming_back_round_to_rgb_mode_starts_again_at_level_1(sim):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device)
    press(device, "A", 9)

    press(device, "B", MODE_COUNT)

    assert brightness(sim, device) < BRIGHTER * at_level_1
