"""Red Light, played on a simulated device.

Red Light shows solid red over its looping music. Any motion ends the game at
once; a device held still survives into the green warning once Red Light's
duration runs out, a duration that shortens as the Game Level rises.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.input import AccelerationData
from packs.scenes.red_light_green_light.tests.helpers import (
    GAME_OVER_STING,
    LEVEL_BAR,
    QUICK_WARNINGS,
    RED,
    RED_MUSIC,
    SLACK,
    WARNING_PEAK,
    last_played_at,
    lit_in,
    survive_round,
    times_played,
    wait_for,
)

RED_LIGHT = {**QUICK_WARNINGS, "rlgl_red_duration": 3.0, "rlgl_max_level": 5}
"""A three-second Red Light, longer than its music clip, with five levels."""

SHORTENING = {
    **QUICK_WARNINGS,
    "rlgl_max_level": 2,
    "rlgl_red_duration": 3.0,
    "rlgl_red_duration_min": 1.0,
    "rlgl_green_duration": 1.0,
    "rlgl_level_up_duration": 0.5,
}
"""Red Light lasts 3.0 s at level one and 1.0 s at the top level, level two."""

THREE_ROUNDS = {**SHORTENING, "rlgl_max_level": 3}


def reach_red_light(sim: Simulation, player: SimulatedDevice) -> None:
    player.tap("A")
    wait_for(sim, player, RED_MUSIC)


def red_light_ends(sim: Simulation, player: SimulatedDevice) -> None:
    sim.run_until(lambda: not lit_in(player, RED))


def test_red_light_shows_solid_red_on_every_light_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)

    reach_red_light(sim, player)

    assert lit_in(player, RED)


def test_red_light_keeps_the_level_bar_showing(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)

    reach_red_light(sim, player)

    assert player.strip(LEVEL_BAR).lit == 2


def test_red_light_loops_its_music(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    sim.advance(player.clip_length(RED_MUSIC) + 0.5)

    assert player.is_playing(RED_MUSIC)


def test_holding_still_through_red_light_survives_into_the_green_warning(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    sim.run_until(lambda: last_played_at(player, WARNING_PEAK) > last_played_at(player, RED_MUSIC))

    assert not player.has_played(GAME_OVER_STING)


def test_red_light_lasts_its_duration(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    red_light_ends(sim, player)

    assert sim.now - last_played_at(player, RED_MUSIC) == pytest.approx(3.0, abs=SLACK)


def test_the_red_music_stops_when_red_light_ends(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    red_light_ends(sim, player)

    assert not player.is_playing(RED_MUSIC)


def test_moving_on_red_light_ends_the_game(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    player.move()
    sim.advance(0.5)

    assert player.has_played(GAME_OVER_STING)


def test_red_light_catches_motion_at_once(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)
    moved_at = sim.now

    player.move()
    wait_for(sim, player, GAME_OVER_STING)

    assert sim.now - moved_at <= 0.1


def test_a_one_tick_jolt_on_red_light_is_not_caught(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)

    player.accelerate(0.0, 0.0, AccelerationData.GRAVITY + 0.5)
    sim.advance(TICK)
    player.hold_still()
    sim.advance(1.0)

    assert not player.has_played(GAME_OVER_STING)


def test_pressing_a_button_on_red_light_changes_nothing(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=RED_LIGHT)
    reach_red_light(sim, player)
    peaks = times_played(player, WARNING_PEAK)

    player.tap("A")
    player.tap("B")

    assert (lit_in(player, RED), player.is_playing(RED_MUSIC)) == (True, True)
    assert times_played(player, WARNING_PEAK) == peaks


def test_red_light_shortens_to_its_minimum_at_the_top_level(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=SHORTENING)
    player.tap("A")
    survive_round(sim, player)

    wait_for(sim, player, RED_MUSIC)
    red_light_ends(sim, player)

    assert sim.now - last_played_at(player, RED_MUSIC) == pytest.approx(1.0, abs=SLACK)


def test_a_tilt_between_rounds_is_not_caught_on_the_next_red_light(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=THREE_ROUNDS)
    player.tap("A")
    survive_round(sim, player)

    player.accelerate(0.0, 4.0, 8.9)
    wait_for(sim, player, RED_MUSIC)
    sim.advance(0.5)

    assert not player.has_played(GAME_OVER_STING)
