"""Being caught, game over, and back to Ready, played on a simulated device.

Moving on Red Light or holding still on Green Light ends the game: fire over
every strip, the game-over sting, and silence from the light's music. After
the game-over pause the device is back in a Ready that starts a fresh game.
"""

from __future__ import annotations

import pytest

from app.simulation import SimulatedDevice, Simulation
from effects.effect import HapticPattern
from packs.scenes.red_light_green_light.tests.helpers import (
    EVERY_STRIP,
    GAME_OVER_STING,
    GREEN_MUSIC,
    LEVEL_BAR,
    LEVEL_UP_SOUND,
    QUICK_WARNINGS,
    READY_SOUND,
    RED_MUSIC,
    SLACK,
    last_played_at,
    survive_round,
    wait_for,
)

GAME = {
    **QUICK_WARNINGS,
    "rlgl_red_duration": 1.0,
    "rlgl_green_duration": 1.0,
    "rlgl_level_up_duration": 0.5,
    "rlgl_green_still_timeout": 0.5,
    "rlgl_game_over_duration": 2.0,
    "rlgl_max_level": 5,
}
"""Five levels, each filling two of the level bar's ten pixels."""


LONG_GAME_OVER = {**GAME, "rlgl_game_over_duration": 5.0}
"""A game-over pause outlasting the sting."""


def caught_on_red_light(simulation: Simulation, player: SimulatedDevice) -> None:
    """Move on the next Red Light, then hold still once caught."""
    wait_for(simulation, player, RED_MUSIC)
    player.move()
    wait_for(simulation, player, GAME_OVER_STING)
    player.hold_still()


def caught_on_green_light(simulation: Simulation, player: SimulatedDevice) -> None:
    """Hold still through the next Green Light until caught."""
    wait_for(simulation, player, GREEN_MUSIC)
    wait_for(simulation, player, GAME_OVER_STING)


def test_the_game_over_sting_buzzes_three_times(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")

    caught_on_red_light(simulation, player)

    buzz, pause = HapticPattern.STRONG_BUZZ, HapticPattern.PAUSE_250
    assert player.buzzed[-1].pattern == (buzz, pause, buzz, pause, buzz)


def test_the_game_over_sting_plays_once(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=LONG_GAME_OVER)
    player.tap("A")
    caught_on_red_light(simulation, player)

    simulation.advance(player.clip_length(GAME_OVER_STING) + SLACK)

    assert not player.is_playing(GAME_OVER_STING)


def test_game_over_burns_fire_across_every_pixel_of_every_strip(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")
    caught_on_red_light(simulation, player)

    simulation.advance(0.5)

    assert all(player.strip(scope).lit == player.strip(scope).size for scope in EVERY_STRIP)


@pytest.mark.parametrize(
    ("get_caught", "music"),
    [(caught_on_red_light, RED_MUSIC), (caught_on_green_light, GREEN_MUSIC)],
    ids=["red", "green"],
)
def test_being_caught_stops_the_lights_music(simulation, get_caught, music):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")

    get_caught(simulation, player)

    assert not player.is_playing(music)


def test_being_caught_on_green_light_does_not_level_up(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")
    caught_on_green_light(simulation, player)

    wait_for(simulation, player, READY_SOUND)

    assert not player.has_played(LEVEL_UP_SOUND)


def test_the_device_returns_to_ready_after_the_game_over_pause(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")
    caught_on_red_light(simulation, player)

    wait_for(simulation, player, READY_SOUND)

    assert simulation.now - last_played_at(player, GAME_OVER_STING) == pytest.approx(2.0, abs=SLACK)


def test_a_game_after_game_over_starts_again_from_level_one(simulation):
    player = simulation.add_device("p1", scene="red_light_green_light", scene_data=GAME)
    player.tap("A")
    survive_round(simulation, player)
    caught_on_red_light(simulation, player)
    wait_for(simulation, player, READY_SOUND)

    player.tap("A")
    survive_round(simulation, player)

    assert player.strip(LEVEL_BAR).lit == 4
