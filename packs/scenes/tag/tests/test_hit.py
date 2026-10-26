"""Tag hits, played on simulated devices.

Tags arrive through ``receive_ir``: encoded with the scene's wire-frame codec
and decoded by the device's real IR stack. Only tags from the expected
shooter count, so every test pins who that is.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import (
    GREEN,
    SHOOTER,
    land,
    shooters_tag,
    start_game,
    tag_shot,
)

TEN_HITPOINTS = {**SHOOTER, "tag_starting_hitpoints": 10}


def test_a_tag_from_the_expected_shooter_plays_the_hit_on_the_main_strip(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    land(sim, player, shooters_tag())

    assert player.has_played("scene.hit_start")
    assert not player.strip(Scope.Global.MAIN).dark


def test_a_hit_buzzes_the_hit_haptic(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    land(sim, player, shooters_tag())

    assert [b.pattern for b in player.buzzed] == [
        (HapticPattern.STRONG_BUZZ, HapticPattern.PAUSE_250, HapticPattern.STRONG_CLICK)
    ]


def test_the_hit_flash_goes_dark_when_the_hit_sound_ends(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    land(sim, player, shooters_tag())
    sim.advance(player.clip_length("scene.hit_start") + TICK)  # cleared the tick after it ends

    assert player.strip(Scope.Global.MAIN).dark


def test_a_hit_drains_the_green_hitpoints_bar_by_its_damage(sim):
    player = sim.add_device("red", scene="tag", scene_data=TEN_HITPOINTS)
    start_game(sim, player)

    land(sim, player, shooters_tag(damage=4))

    bar = player.strip(Scope.PERSONAL)
    assert bar.lit == bar.size - 4 * bar.size // 10
    assert set(bar.pixels) <= {0, GREEN}


def test_a_hit_on_the_first_tick_of_playing_costs_a_hitpoint(sim):
    player = sim.add_device("red", scene="tag", scene_data=TEN_HITPOINTS)
    player.tap("A")

    # A tag every tick through the countdown: the first to play the hit is the
    # first to land in Playing.
    deadline = sim.now + 10.0
    while not player.has_played("scene.hit_start"):
        assert sim.now < deadline, "no tag landed in Playing"
        player.receive_ir(shooters_tag())
        sim.advance(TICK)

    bar = player.strip(Scope.PERSONAL)
    assert bar.lit == bar.size - bar.size // 10


def test_successive_hits_keep_draining_the_hitpoints_bar(sim):
    player = sim.add_device("red", scene="tag", scene_data=TEN_HITPOINTS)
    start_game(sim, player)

    for _ in range(3):
        land(sim, player, shooters_tag())

    bar = player.strip(Scope.PERSONAL)
    assert bar.lit == bar.size - 3 * bar.size // 10


@pytest.mark.parametrize(
    "shot",
    [tag_shot(team=1, player=3, damage=1), tag_shot(team=2, player=4, damage=1)],
    ids=["another team", "another player"],
)
def test_a_tag_from_anyone_but_the_expected_shooter_does_no_harm(sim, shot):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    land(sim, player, shot)

    assert not player.has_played("scene.hit_start")
    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_players_own_shot_never_hits_themselves(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.tap("A")  # the shot carries the shooter's tag and lights the device's own receivers
    sim.advance(TICK)

    assert not player.has_played("scene.hit_start")
    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_tag_before_the_game_starts_does_nothing(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)

    land(sim, player, shooters_tag())

    assert not player.has_played("scene.hit_start")


def test_a_hit_mid_reload_does_not_interrupt_the_reload(sim):
    one_round = {"tag_max_ammo": 1, "tag_reload_duration": 1.0}
    player = sim.add_device("red", scene="tag", scene_data={**TEN_HITPOINTS, **one_round})
    start_game(sim, player)
    player.tap("A")  # fires the only round

    player.hold("A")
    sim.advance(one_round["tag_reload_duration"] / 2)
    land(sim, player, shooters_tag())

    sim.run_until(
        lambda: player.has_played("scene.reload_complete"),
        timeout=one_round["tag_reload_duration"],
    )
