"""Level Up and Win, played on a simulated device.

Surviving Green Light below the top level levels up: a gold flash, a longer
level bar, and the next round. Surviving it at the top level wins: lightning
and the win sting, then back to a playable Ready once the sting ends.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from effects.effect import HapticPattern
from packs.scenes.red_light_green_light.tests.helpers import (
    EVERY_STRIP,
    GAME_OVER_STING,
    LEVEL_BAR,
    LEVEL_UP_SOUND,
    LIGHT_STRIPS,
    QUICK_WARNINGS,
    READY_SOUND,
    RED_MUSIC,
    SLACK,
    WIN_STING,
    last_played_at,
    survive_round,
    times_played,
    wait_for,
)

ROUNDS = {
    **QUICK_WARNINGS,
    "rlgl_red_duration": 1.0,
    "rlgl_green_duration": 1.0,
    "rlgl_level_up_duration": 1.0,
}

FIVE_LEVELS = {**ROUNDS, "rlgl_max_level": 5}
"""Each level fills two of the level bar's ten pixels."""

LONG_LEVEL_UP = {**FIVE_LEVELS, "rlgl_level_up_duration": 3.0}
"""A Level Up outlasting its sound."""

ONE_LEVEL = {**ROUNDS, "rlgl_max_level": 1}
"""The first round is the last, so surviving it wins."""

TWO_LEVELS = {**ROUNDS, "rlgl_max_level": 2}

THREE_LEVELS = {**ROUNDS, "rlgl_max_level": 3}


def gold(pixel: int) -> bool:
    red, green, blue = pixel >> 16, (pixel >> 8) & 0xFF, pixel & 0xFF
    return red > green > 0 and blue == 0


def win_the_only_round(sim: Simulation, player: SimulatedDevice) -> None:
    player.tap("A")
    survive_round(sim, player)


# ---------------------------------------------------------------------------
# Level Up
# ---------------------------------------------------------------------------


def test_surviving_green_light_below_the_top_level_levels_up(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")

    survive_round(sim, player)

    assert (player.has_played(LEVEL_UP_SOUND), player.has_played(WIN_STING)) == (True, False)


def test_a_level_up_double_clicks_the_haptic(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")

    survive_round(sim, player)

    assert player.buzzed[-1].pattern == (HapticPattern.DOUBLE_CLICK,)


def test_the_level_up_sound_plays_once(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=LONG_LEVEL_UP)
    player.tap("A")
    survive_round(sim, player)

    sim.advance(player.clip_length(LEVEL_UP_SOUND) + SLACK)

    assert not player.is_playing(LEVEL_UP_SOUND)


def test_a_level_up_flashes_gold_on_every_light_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")
    survive_round(sim, player)

    sim.advance(0.3)

    assert all(any(gold(p) for p in player.strip(scope).pixels) for scope in LIGHT_STRIPS)


def test_a_level_up_shows_only_gold_on_the_light_strips(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")
    survive_round(sim, player)

    sim.advance(0.3)

    assert all(all(gold(p) for p in player.strip(scope).pixels) for scope in LIGHT_STRIPS)


def test_a_level_up_grows_the_level_bar_by_one_level(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")

    survive_round(sim, player)

    assert player.strip(LEVEL_BAR).lit == 4


def test_the_next_round_starts_once_the_level_up_is_over(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")
    survive_round(sim, player)

    wait_for(sim, player, RED_MUSIC)

    level_up_and_warning = 1.0 + 3 * QUICK_WARNINGS["rlgl_warning_pulse_max"]
    assert sim.now - last_played_at(player, LEVEL_UP_SOUND) == pytest.approx(
        level_up_and_warning, abs=SLACK
    )


def test_moving_during_a_level_up_is_not_caught(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=FIVE_LEVELS)
    player.tap("A")
    survive_round(sim, player)

    player.move()
    wait_for(sim, player, RED_MUSIC)

    assert not player.has_played(GAME_OVER_STING)


# ---------------------------------------------------------------------------
# Win
# ---------------------------------------------------------------------------


def test_surviving_green_light_at_the_top_level_wins(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_LEVEL)

    win_the_only_round(sim, player)

    assert (player.has_played(WIN_STING), player.has_played(LEVEL_UP_SOUND)) == (True, False)


def test_a_win_triple_clicks_the_haptic(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_LEVEL)

    win_the_only_round(sim, player)

    assert player.buzzed[-1].pattern == (HapticPattern.TRIPLE_CLICK,)


def test_a_win_strikes_lightning_across_every_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_LEVEL)
    win_the_only_round(sim, player)

    lit, dark = set(), set()
    for _ in range(int(2.0 / TICK)):
        sim.advance(TICK)
        for scope in EVERY_STRIP:
            (dark if player.strip(scope).dark else lit).add(str(scope))

    every = {str(scope) for scope in EVERY_STRIP}
    assert (lit, dark) == (every, every)


def test_the_device_returns_to_ready_the_moment_the_win_sting_ends(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_LEVEL)
    win_the_only_round(sim, player)

    wait_for(sim, player, READY_SOUND)

    sting_length = player.clip_length(WIN_STING)
    assert sim.now - last_played_at(player, WIN_STING) == pytest.approx(sting_length, abs=SLACK)


def test_moving_during_a_win_is_not_caught(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_LEVEL)
    win_the_only_round(sim, player)

    player.move()
    wait_for(sim, player, READY_SOUND)

    assert not player.has_played(GAME_OVER_STING)


def test_a_full_game_levels_up_every_round_but_the_last_then_wins(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=THREE_LEVELS)
    player.tap("A")

    for _ in range(3):
        survive_round(sim, player)

    assert (times_played(player, LEVEL_UP_SOUND), times_played(player, WIN_STING)) == (2, 1)


def test_a_game_after_a_win_starts_again_from_level_one(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=TWO_LEVELS)
    player.tap("A")
    survive_round(sim, player)
    survive_round(sim, player)
    wait_for(sim, player, READY_SOUND)
    player.forget()

    player.tap("A")
    survive_round(sim, player)

    assert (player.has_played(LEVEL_UP_SOUND), player.has_played(WIN_STING)) == (True, False)
