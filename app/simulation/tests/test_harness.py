"""The Simulation test harness's input and query surface, driven through Tag."""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.network import LINE
from engine.state import Scope
from packs.scenes.tag.tag_data import TagData, encode_tag_data


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    for player in players:
        player.tap("A")
    sim.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


def shot_count(player: SimulatedDevice) -> int:
    return sum(1 for s in player.ir_sent if s.emitter == LINE)


def test_tap_returns_once_the_press_has_registered(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")

    assert shot_count(player) == 1


def test_tap_returns_once_the_release_has_registered(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_shot_cooldown": 0.0})
    start_game(sim, player)

    player.tap("A")
    player.tap("A")

    assert shot_count(player) == 2


def test_tap_advances_every_device_in_lockstep(sim):
    red = sim.add_device("red", scene="tag")
    blue = sim.add_device("blue", scene="tag", scene_data={"tag_expected_team": 1})
    start_game(sim, red, blue)

    blue.hold("A")
    red.tap("A")

    assert shot_count(blue) == 1


def test_hold_and_release_only_schedule_the_pin_change(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)
    before = sim.now

    player.hold("A")
    player.release("A")

    assert sim.now == before
    assert shot_count(player) == 0


def test_a_device_does_not_hear_its_own_shot(sim):
    # Red's own shot is a matching tag for red, so hearing it would count as a hit.
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.tap("A")
    sim.advance(0.5)

    assert shot_count(player) == 1
    assert not player.has_played("scene.hit_start")


def test_payloads_received_together_arrive_on_successive_ticks(sim):
    # Each matching one-damage tag takes one of ten pips off the hitpoint bar.
    player = sim.add_device("red", scene="tag", scene_data={"tag_starting_hitpoints": 10})
    start_game(sim, player)

    player.receive_ir(bytes(encode_tag_data(TagData(0, 1, 1))))
    player.receive_ir(bytes(encode_tag_data(TagData(0, 1, 1))))
    sim.advance(TICK)
    after_first_tick = player.strip(Scope.PERSONAL).lit
    sim.advance(TICK)

    assert (after_first_tick, player.strip(Scope.PERSONAL).lit) == (9, 8)


def test_clip_length_reads_the_clips_wav_header(sim):
    player = sim.add_device("red", scene="tag")

    # fire_shot_start.wav: 3456 frames of 11025 Hz mono
    assert player.clip_length("scene.fire_shot_start") == pytest.approx(3456 / 11025)


def reach_red_light(sim: Simulation, player: SimulatedDevice) -> None:
    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.red_light_music_start"))


def test_a_moving_device_reads_as_motion_to_the_scene(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    reach_red_light(sim, player)

    player.move()

    sim.run_until(lambda: player.has_played("basic.game_over_sting_start"), timeout=1.0)


def test_a_still_device_does_not_read_as_motion_to_the_scene(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    reach_red_light(sim, player)

    sim.advance(2.0)

    assert not player.has_played("basic.game_over_sting_start")
