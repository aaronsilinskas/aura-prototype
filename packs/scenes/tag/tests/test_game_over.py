"""Running out of hitpoints, game over, and back to Ready, played on simulated devices.

Hits arrive through the real IR path (``receive_ir``) until hitpoints run
out. The game-over sting plays over a device lit end to end, and the moment
it ends the device is back in a Ready that starts the next game.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import (
    AMMO_AMBER,
    EVERY_STRIP,
    GREEN,
    SHOOTER,
    hit,
    shooters_tag,
    start_game,
    sweeping_red,
)

STING = "basic.game_over_sting_start"

TWO_HITS_TO_LOSE = {**SHOOTER, "tag_starting_hitpoints": 2}
"""Two one-damage tags from the pinned shooter end the game."""

MID_RELOAD = {**TWO_HITS_TO_LOSE, "tag_max_ammo": 1, "tag_reload_duration": 1.0}
"""One round, so a fresh press after it starts a reload."""


def run_out_of_hitpoints(simulation: Simulation, player: SimulatedDevice) -> None:
    hit(simulation, player, shooters_tag())
    hit(simulation, player, shooters_tag())


def start_reloading(simulation: Simulation, player: SimulatedDevice) -> None:
    """Fire the only round, then hold the trigger halfway through the reload."""
    player.tap("A")
    player.hold("A")
    simulation.advance(MID_RELOAD["tag_reload_duration"] / 2)


def sting_ends(simulation: Simulation, player: SimulatedDevice) -> None:
    simulation.run_until(lambda: player.has_played("scene.ready_shots_start"))


# ---------------------------------------------------------------------------
# Game over
# ---------------------------------------------------------------------------


def test_the_last_hitpoint_lost_plays_the_game_over_sting(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)

    run_out_of_hitpoints(simulation, player)

    assert player.has_played(STING)


def test_the_game_over_sting_buzzes_three_times(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)

    run_out_of_hitpoints(simulation, player)

    buzz, pause = HapticPattern.STRONG_BUZZ, HapticPattern.PAUSE_250
    assert player.buzzed[-1].pattern == (buzz, pause, buzz, pause, buzz)


def test_a_hit_that_leaves_hitpoints_does_not_end_the_game(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)

    hit(simulation, player, shooters_tag())

    assert not player.has_played(STING)


def test_damage_past_zero_ends_the_game_too(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)

    hit(simulation, player, shooters_tag(damage=4))

    assert player.has_played(STING)


def test_game_over_lights_every_pixel_of_every_strip(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)

    run_out_of_hitpoints(simulation, player)

    assert all(player.strip(scope).lit == player.strip(scope).size for scope in EVERY_STRIP)


def test_a_reload_in_progress_when_the_game_ends_never_completes(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=MID_RELOAD)
    start_game(simulation, player)
    start_reloading(simulation, player)

    run_out_of_hitpoints(simulation, player)
    simulation.advance(MID_RELOAD["tag_reload_duration"])

    assert not player.has_played("scene.reload_complete")


def test_a_reload_in_progress_when_the_game_ends_stops_its_loop(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=MID_RELOAD)
    start_game(simulation, player)
    start_reloading(simulation, player)
    reloading = player.is_playing("scene.reload")

    run_out_of_hitpoints(simulation, player)

    assert (reloading, player.is_playing("scene.reload")) == (True, False)


# ---------------------------------------------------------------------------
# Back to Ready
# ---------------------------------------------------------------------------


def test_the_device_returns_to_ready_the_moment_the_sting_ends(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)
    run_out_of_hitpoints(simulation, player)

    sting_ends(simulation, player)

    at = {p.clip: p.at for p in player.played}
    sting_length = player.clip_length(STING)
    assert at["scene.ready_shots_start"] - at[STING] == pytest.approx(sting_length, abs=2 * TICK)


def test_after_the_sting_the_device_sweeps_red_again(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)
    run_out_of_hitpoints(simulation, player)

    sting_ends(simulation, player)

    assert all(sweeping_red(player.strip(scope)) for scope in EVERY_STRIP)


def test_a_press_after_game_over_starts_a_fresh_game(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=TWO_HITS_TO_LOSE)
    start_game(simulation, player)
    run_out_of_hitpoints(simulation, player)
    sting_ends(simulation, player)

    start_game(simulation, player)

    assert player.strip(Scope.PERSONAL).all_lit(GREEN)
    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_a_reload_cut_short_by_game_over_does_not_finish_in_the_next_game(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=MID_RELOAD)
    start_game(simulation, player)
    start_reloading(simulation, player)
    run_out_of_hitpoints(simulation, player)
    player.release("A")
    sting_ends(simulation, player)

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert not player.has_played("scene.reload_complete")
