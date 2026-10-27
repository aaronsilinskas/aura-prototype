"""RGB mode, where a device switches on: five element effects, and A steps their level.

Water shows on personal, fire on directional, lightning on global main, earth
on global buff and ice on global debuff. A steps the level 1 to 10 and back
to 1. The flames burn about twice as bright at level 10 as at level 1, so
brightness over a second tells the two apart.
"""

from __future__ import annotations

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.state import Scope
from packs.scenes.hardware_test.tests.helpers import SFX, enter_mode

ELEMENT_STRIPS = [
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.Global.MAIN,
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
]
BLUE = 0x0000FF

WATCH = 2.0
"""Long enough for level-1 lightning, hidden for up to 1.5 seconds, to strike."""

BRIGHTER = 1.5
"""How many times brighter than level 1 counts as the top level: level 10 burns about 2x."""


def brightness(sim: Simulation, device: SimulatedDevice) -> float:
    """Watch the element strips for a second; return their mean summed channels per tick."""
    ticks = round(1.0 / TICK)
    total = 0
    for _ in range(ticks):
        sim.advance(TICK)
        for scope in ELEMENT_STRIPS:
            for pixel in device.strip(scope).pixels:
                total += (pixel >> 16) + ((pixel >> 8) & 0xFF) + (pixel & 0xFF)
    return total / ticks


def tap_a(device: SimulatedDevice, times: int) -> None:
    for _ in range(times):
        device.tap("A")


def test_on_switch_on_the_personal_strip_shows_water_in_shades_of_blue(sim):
    device = sim.add_device("red", scene="hardware_test")

    sim.advance(0.5)

    personal = device.strip(Scope.PERSONAL)
    assert not personal.dark and personal.shades_of(BLUE)


def test_on_switch_on_every_element_strip_lights_and_ambient_stays_dark(sim):
    # Lightning strikes now and then, so each strip only has to light at some point.
    device = sim.add_device("red", scene="hardware_test")
    seen_lit: set[str] = set()
    ambient_lit = False

    for _ in range(round(WATCH / TICK)):
        sim.advance(TICK)
        seen_lit |= {s.keys[0] for s in ELEMENT_STRIPS if not device.strip(s).dark}
        ambient_lit = ambient_lit or not device.strip(Scope.AMBIENT).dark

    assert (len(seen_lit), ambient_lit) == (len(ELEMENT_STRIPS), False)


def test_nine_presses_of_a_take_the_level_from_1_to_the_top_and_the_flames_burn_brighter(sim):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device)

    tap_a(device, 9)

    assert brightness(sim, device) > BRIGHTER * at_level_1


def test_a_tenth_press_wraps_the_level_back_to_1(sim):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device)

    tap_a(device, 10)

    assert brightness(sim, device) < BRIGHTER * at_level_1


def test_coming_back_round_to_rgb_mode_starts_again_at_level_1(sim):
    device = sim.add_device("red", scene="hardware_test")
    at_level_1 = brightness(sim, device)
    tap_a(device, 9)

    enter_mode(device, SFX + 1)

    assert brightness(sim, device) < BRIGHTER * at_level_1
