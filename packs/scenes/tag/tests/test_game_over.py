"""Running out of hitpoints, game over, and back to Ready, played on simulated devices.

Hits arrive through the real IR path (``receive_ir``) until hitpoints run
out. The game-over sting plays over a burning device, and the moment it ends
the device is back in a Ready that starts the next game.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation, Strip
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import start_game, tag

AMMO_AMBER = 0xFFBF00
GREEN = 0x00FF00
STING = "basic.game_over_sting_start"

TWO_HITPOINTS = {"tag_expected_team": 2, "tag_expected_player": 3, "tag_starting_hitpoints": 2}
"""Two one-damage hits from the expected shooter end the game."""

EVERY_STRIP = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
]


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def hit(sim: Simulation, player: SimulatedDevice, damage: int = 1) -> None:
    player.receive_ir(tag(2, 3, damage))
    sim.advance(0.1)


def run_out_of_hitpoints(sim: Simulation, player: SimulatedDevice) -> None:
    hit(sim, player)
    hit(sim, player)


def burning(strip: Strip) -> bool:
    """Every pixel lit: fire's smouldering roots never go dark."""
    return strip.lit == strip.size


def sting_ends(sim: Simulation, player: SimulatedDevice) -> None:
    sim.run_until(lambda: player.has_played("scene.ready_shots_start"))


# ---------------------------------------------------------------------------
# Game over
# ---------------------------------------------------------------------------


def test_the_last_hitpoint_lost_plays_the_game_over_sting(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)

    run_out_of_hitpoints(sim, player)

    assert player.has_played(STING)


def test_the_game_over_sting_buzzes_three_times(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)

    run_out_of_hitpoints(sim, player)

    buzz, pause = HapticPattern.STRONG_BUZZ, HapticPattern.PAUSE_250
    assert player.buzzed[-1].pattern == (buzz, pause, buzz, pause, buzz)


def test_a_hit_that_leaves_hitpoints_does_not_end_the_game(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)

    hit(sim, player)

    assert not player.has_played(STING)


def test_damage_past_zero_ends_the_game_too(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)

    hit(sim, player, damage=4)

    assert player.has_played(STING)


def test_game_over_sets_every_strip_burning(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)

    run_out_of_hitpoints(sim, player)

    assert all(burning(player.strip(scope)) for scope in EVERY_STRIP)


def test_a_reload_in_progress_when_the_game_ends_never_completes(sim):
    one_round = {"tag_max_ammo": 1, "tag_reload_duration": 1.0}
    player = sim.add_device("red", scene="tag", scene_data={**TWO_HITPOINTS, **one_round})
    start_game(sim, player)
    player.tap("A")  # fires the only round

    player.hold("A")
    sim.advance(0.5)
    run_out_of_hitpoints(sim, player)
    sim.advance(1.0)

    assert not player.has_played("scene.reload_complete")


# ---------------------------------------------------------------------------
# Back to Ready
# ---------------------------------------------------------------------------


def test_the_device_returns_to_ready_the_moment_the_sting_ends(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)
    run_out_of_hitpoints(sim, player)

    sting_ends(sim, player)

    at = {p.clip: p.at for p in player.played}
    sting_length = player.clip_length(STING)
    assert at["scene.ready_shots_start"] - at[STING] == pytest.approx(sting_length, abs=2 * TICK)


def test_after_the_sting_the_device_sweeps_red_again(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)
    run_out_of_hitpoints(sim, player)

    sting_ends(sim, player)
    sim.advance(0.5)

    assert all(not burning(player.strip(scope)) for scope in EVERY_STRIP)
    assert all(p & 0x00FFFF == 0 for scope in EVERY_STRIP for p in player.strip(scope).pixels)


def test_a_press_after_game_over_starts_a_fresh_game(sim):
    player = sim.add_device("red", scene="tag", scene_data=TWO_HITPOINTS)
    start_game(sim, player)
    run_out_of_hitpoints(sim, player)
    sting_ends(sim, player)

    start_game(sim, player)

    assert player.strip(Scope.PERSONAL).all_lit(GREEN)
    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_a_reload_cut_short_by_game_over_does_not_finish_in_the_next_game(sim):
    one_round = {"tag_max_ammo": 1, "tag_reload_duration": 1.0}
    player = sim.add_device("red", scene="tag", scene_data={**TWO_HITPOINTS, **one_round})
    start_game(sim, player)
    player.tap("A")  # fires the only round
    player.hold("A")
    sim.advance(0.5)
    run_out_of_hitpoints(sim, player)
    player.release("A")
    sting_ends(sim, player)

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))
    sim.advance(0.5)

    assert not player.has_played("scene.reload_complete")
