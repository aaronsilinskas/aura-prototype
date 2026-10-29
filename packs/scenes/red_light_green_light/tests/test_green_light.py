"""Green Light, played on a simulated device.

Green Light shows solid green over its looping music. The player must keep
moving: stillness lasting the still timeout ends the game, while a shorter
pause is forgiven. Green Light's duration shortens as the Game Level rises.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.input import AccelerationData
from packs.scenes.red_light_green_light.tests.helpers import (
    GAME_OVER_STING,
    GREEN,
    GREEN_MUSIC,
    LEVEL_UP_SOUND,
    QUICK_WARNINGS,
    SLACK,
    WIN_STING,
    last_played_at,
    lit_in,
    survive_round,
    wait_for,
)

GREEN_LIGHT = {
    **QUICK_WARNINGS,
    "rlgl_red_duration": 1.0,
    "rlgl_green_duration": 3.0,
    "rlgl_green_still_timeout": 0.75,
    "rlgl_max_level": 5,
}

SETTLING = 0.1
"""How long the smoothed motion takes to fall below the move threshold once ``move`` stops."""

LONG_GREEN_LIGHT = {**GREEN_LIGHT, "rlgl_green_duration": 6.0}
"""Green Light outlasting its music clip."""

SHORTENING = {
    **GREEN_LIGHT,
    "rlgl_max_level": 2,
    "rlgl_green_duration_min": 1.0,
    "rlgl_level_up_duration": 0.5,
}
"""Green Light lasts 3.0 s at level one and 1.0 s at the top level, level two."""


def reach_green_light(simulation: Simulation, player: SimulatedDevice) -> None:
    player.tap("A")
    wait_for(simulation, player, GREEN_MUSIC)


def test_green_light_shows_solid_green_on_every_light_strip(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)

    reach_green_light(simulation, player)

    assert lit_in(player, GREEN)


def test_green_light_loops_its_music(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=LONG_GREEN_LIGHT)
    reach_green_light(simulation, player)

    player.move()
    simulation.advance(player.clip_length(GREEN_MUSIC) + 0.5)

    assert player.is_playing(GREEN_MUSIC)


def test_moving_through_green_light_survives_it(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)

    player.move()
    wait_for(simulation, player, LEVEL_UP_SOUND)

    assert not player.has_played(GAME_OVER_STING)


def test_holding_still_on_green_light_ends_the_game_after_the_still_timeout(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)

    wait_for(simulation, player, GAME_OVER_STING)

    assert simulation.now - last_played_at(player, GREEN_MUSIC) == pytest.approx(0.75, abs=SLACK)


def test_stopping_on_green_light_ends_the_game_a_still_timeout_later(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)
    player.move()
    simulation.advance(1.0)
    stopped_at = simulation.now

    player.hold_still()
    wait_for(simulation, player, GAME_OVER_STING)

    assert simulation.now - stopped_at == pytest.approx(0.75, abs=SETTLING)


def test_a_pause_shorter_than_the_still_timeout_is_forgiven(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)
    player.move()
    simulation.advance(0.5)

    player.hold_still()
    simulation.advance(0.5)
    player.move()
    wait_for(simulation, player, LEVEL_UP_SOUND)

    assert not player.has_played(GAME_OVER_STING)


def test_a_gentle_sway_on_green_light_counts_as_still(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)

    player.move(strength=1.0)
    wait_for(simulation, player, GAME_OVER_STING)

    assert simulation.now - last_played_at(player, GREEN_MUSIC) == pytest.approx(0.75, abs=SLACK)


def test_a_one_tick_jolt_on_green_light_does_not_count_as_moving(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)
    simulation.advance(0.5)

    player.accelerate(0.0, 0.0, AccelerationData.GRAVITY + 3.0)
    simulation.advance(TICK)
    player.hold_still()
    wait_for(simulation, player, GAME_OVER_STING)

    assert simulation.now - last_played_at(player, GREEN_MUSIC) == pytest.approx(0.75, abs=SLACK)


def test_green_light_lasts_its_duration(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)

    player.move()
    wait_for(simulation, player, LEVEL_UP_SOUND)

    assert simulation.now - last_played_at(player, GREEN_MUSIC) == pytest.approx(3.0, abs=SLACK)


def test_the_green_music_stops_when_green_light_ends(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GREEN_LIGHT)
    reach_green_light(simulation, player)

    player.move()
    wait_for(simulation, player, LEVEL_UP_SOUND)

    assert not player.is_playing(GREEN_MUSIC)


def test_green_light_shortens_to_its_minimum_at_the_top_level(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=SHORTENING)
    player.tap("A")
    survive_round(simulation, player)

    wait_for(simulation, player, GREEN_MUSIC)
    player.move()
    wait_for(simulation, player, WIN_STING)

    assert simulation.now - last_played_at(player, GREEN_MUSIC) == pytest.approx(1.0, abs=SLACK)
