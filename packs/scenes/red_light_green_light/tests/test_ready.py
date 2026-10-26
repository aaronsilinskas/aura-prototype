"""Booting into Red Light Green Light and starting a game, played on a simulated device.

A device boots into Ready, pulsing red then green, and a button press starts
the first round's red warning with the level bar at level one.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK
from packs.scenes.red_light_green_light.tests.helpers import (
    EVERY_STRIP,
    GAME_OVER_STING,
    LEVEL_BAR,
    READY_SOUND,
    WARNING_PEAK,
)

FIVE_LEVELS = {"rlgl_max_level": 5}
"""Each level fills two of the level bar's ten pixels."""


def only_red(pixels: list[int]) -> bool:
    return all(p != 0 and p & 0x00FFFF == 0 for p in pixels)


def only_green(pixels: list[int]) -> bool:
    return all(p != 0 and p & 0xFF00FF == 0 for p in pixels)


def test_a_booted_device_plays_the_ready_sound(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(TICK)

    assert player.has_played(READY_SOUND)


def test_ready_pulses_red_then_green_on_every_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(0.4)
    red_pulse = all(only_red(player.strip(scope).pixels) for scope in EVERY_STRIP)
    sim.advance(1.0)
    green_pulse = all(only_green(player.strip(scope).pixels) for scope in EVERY_STRIP)

    assert (red_pulse, green_pulse) == (True, True)


def test_an_idle_device_stays_in_ready(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(10.0)

    assert [p.clip for p in player.played] == [READY_SOUND]


def test_moving_in_ready_neither_starts_nor_ends_a_game(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    player.move()
    sim.advance(5.0)

    assert [p.clip for p in player.played] == [READY_SOUND]
    assert not player.has_played(GAME_OVER_STING)


@pytest.mark.parametrize("button", ["A", "B"])
def test_pressing_either_button_in_ready_starts_the_red_warning(sim, button):
    player = sim.add_device("p1", scene="red_light_green_light")

    player.tap(button)
    sim.advance(1.0)

    assert player.has_played(WARNING_PEAK)


def test_a_new_game_starts_the_level_bar_at_level_one(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)

    player.tap("A")

    assert player.strip(LEVEL_BAR).lit == 2
