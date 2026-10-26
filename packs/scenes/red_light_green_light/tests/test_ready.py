"""Booting into Red Light Green Light and starting a game, played on a simulated device.

A device boots into Ready, pulsing red then green, and a button press starts
the first round's red warning with the level bar at level one.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, Strip
from packs.scenes.red_light_green_light.tests.helpers import (
    EVERY_STRIP,
    GREEN,
    LEVEL_BAR,
    READY_SOUND,
    RED,
    SLACK,
    WARNING_PEAK,
    wait_for,
)

FIVE_LEVELS = {"rlgl_max_level": 5}
"""Each level fills two of the level bar's ten pixels."""

READY_PULSE = 1.0
"""How long Ready's pulse takes to brighten, hold and fade, alternating red and green."""

FIRST_PULSE_ON = 0.4
"""Partway through the first pulse's hold, when it is at full brightness."""


def pulsing(strip: Strip, color: int) -> bool:
    """Every pixel lit, each a shade of *color*."""
    return strip.lit == strip.size and strip.shades_of(color)


def test_a_booted_device_plays_the_ready_sound(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(TICK)

    assert player.has_played(READY_SOUND)


def test_the_ready_sound_plays_once(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    wait_for(sim, player, READY_SOUND)

    sim.advance(player.clip_length(READY_SOUND) + SLACK)

    assert not player.is_playing(READY_SOUND)


def test_ready_first_pulses_red_on_every_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(FIRST_PULSE_ON)

    assert all(pulsing(player.strip(scope), RED) for scope in EVERY_STRIP)


def test_ready_follows_the_red_pulse_with_a_green_one_on_every_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(FIRST_PULSE_ON + READY_PULSE)

    assert all(pulsing(player.strip(scope), GREEN) for scope in EVERY_STRIP)


def test_an_idle_device_stays_in_ready(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    sim.advance(10.0)

    assert [p.clip for p in player.played] == [READY_SOUND]


def test_moving_in_ready_does_nothing(sim):
    player = sim.add_device("p1", scene="red_light_green_light")

    player.move()
    sim.advance(5.0)

    assert [p.clip for p in player.played] == [READY_SOUND]


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
