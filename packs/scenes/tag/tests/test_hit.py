"""Tag hits, played on simulated devices.

Tags arrive through ``receive_ir``: encoded with the scene's wire-frame codec
and decoded by the device's real IR stack. Only tags from the expected
shooter count, so every test pins who that is.
"""

from __future__ import annotations

import pytest

from app.simulation import Simulation
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import start_game, tag

GREEN = 0x00FF00

SHOOTER = {"tag_expected_team": 2, "tag_expected_player": 3}
"""The one team/player whose tags count against this device."""

TEN_HITPOINTS = {**SHOOTER, "tag_starting_hitpoints": 10}


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def test_a_tag_from_the_expected_shooter_plays_the_hit_on_the_main_strip(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.receive_ir(tag(2, 3, 1))
    sim.advance(0.1)

    assert player.has_played("scene.hit_start")
    assert not player.strip(Scope.Global.MAIN).dark


def test_a_hit_buzzes_the_hit_haptic(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.receive_ir(tag(2, 3, 1))
    sim.advance(0.1)

    assert [b.pattern for b in player.buzzed] == [
        (HapticPattern.STRONG_BUZZ, HapticPattern.PAUSE_250, HapticPattern.STRONG_CLICK)
    ]


def test_the_hit_flash_goes_dark_when_the_hit_sound_ends(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.receive_ir(tag(2, 3, 1))
    sim.advance(0.1 + player.clip_length("scene.hit_start"))

    assert player.strip(Scope.Global.MAIN).dark


def test_a_hit_drains_the_green_hitpoints_bar_by_its_damage(sim):
    player = sim.add_device("red", scene="tag", scene_data=TEN_HITPOINTS)
    start_game(sim, player)

    player.receive_ir(tag(2, 3, 4))
    sim.advance(0.1)

    bar = player.strip(Scope.PERSONAL)
    assert bar.lit == bar.size - 4 * bar.size // 10
    assert set(bar.pixels) <= {0, GREEN}


def test_successive_hits_keep_draining_the_hitpoints_bar(sim):
    player = sim.add_device("red", scene="tag", scene_data=TEN_HITPOINTS)
    start_game(sim, player)

    for _ in range(3):
        player.receive_ir(tag(2, 3, 1))
        sim.advance(0.1)

    bar = player.strip(Scope.PERSONAL)
    assert bar.lit == bar.size - 3 * bar.size // 10


@pytest.mark.parametrize(
    "shot",
    [tag(1, 3, 1), tag(2, 4, 1)],
    ids=["another team", "another player"],
)
def test_a_tag_from_anyone_but_the_expected_shooter_does_no_harm(sim, shot):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.receive_ir(shot)
    sim.advance(0.1)

    assert not player.has_played("scene.hit_start")
    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_players_own_shot_never_hits_themselves(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    start_game(sim, player)

    player.tap("A")  # the shot carries the shooter's tag and lights the device's own receivers
    sim.advance(0.5)

    assert not player.has_played("scene.hit_start")
    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_a_tag_before_the_game_starts_does_nothing(sim):
    player = sim.add_device("red", scene="tag", scene_data=SHOOTER)
    sim.advance(0.5)

    player.receive_ir(tag(2, 3, 1))
    sim.advance(0.1)

    assert not player.has_played("scene.hit_start")


def test_a_hit_mid_reload_does_not_interrupt_the_reload(sim):
    reload_second = {"tag_max_ammo": 1, "tag_reload_duration": 1.0}
    player = sim.add_device("red", scene="tag", scene_data={**TEN_HITPOINTS, **reload_second})
    start_game(sim, player)
    player.tap("A")  # fires the only round

    player.hold("A")
    sim.advance(0.5)
    player.receive_ir(tag(2, 3, 1))
    sim.advance(1.0)

    assert player.has_played("scene.hit_start")
    assert player.has_played("scene.reload_complete")
