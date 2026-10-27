"""The Simulation test harness's input and query surface.

Driven through Tag, and through Red Light Green Light for the accelerometer:
its Red phase ends the game on any motion, and its Red Warning ignores motion,
so a test sets the accelerometer up during Warning and watches Red.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.network import LINE
from engine.state import Scope
from packs.scenes.tag.tag_data import TagData, encode_tag_data


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


ONE_ROUND = {"tag_max_ammo": 1, "tag_reload_duration": 1.0}
"""One round, so a fresh press after it starts a one-second reload."""


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    for player in players:
        player.tap("A")
    sim.run_until(lambda: all(p.has_played("scene.go_start") for p in players))
    for player in players:
        player.forget()


def shot_count(player: SimulatedDevice) -> int:
    return sum(1 for s in player.ir_sent if s.emitter == LINE)


def reload_part_way(sim: Simulation, player: SimulatedDevice) -> None:
    """Fire the only round, then hold the trigger halfway through the reload."""
    player.tap("A")
    player.hold("A")
    sim.advance(0.5)


def start_red_light_warning(player: SimulatedDevice) -> None:
    player.tap("A")


def reach_red_light(sim: Simulation, player: SimulatedDevice) -> None:
    sim.run_until(lambda: player.has_played("scene.red_light_music_start"))


def caught_moving(player: SimulatedDevice) -> bool:
    return player.has_played("basic.game_over_sting_start")


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

    blue.schedule_hold("A")
    red.tap("A")

    assert shot_count(blue) == 1


def test_hold_returns_once_the_press_has_registered(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)

    player.hold("A")

    assert shot_count(player) == 1


def test_release_returns_once_the_release_has_registered(sim):
    player = sim.add_device("red", scene="tag", scene_data=ONE_ROUND)
    start_game(sim, player)
    reload_part_way(sim, player)

    player.release("A")

    assert not player.is_playing("scene.reload")


def test_schedule_hold_and_schedule_release_only_schedule_the_pin_change(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)
    before = sim.now

    player.schedule_hold("A")
    player.schedule_release("A")

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


def test_a_one_shot_clip_is_playing_until_it_runs_out(sim):
    player = sim.add_device("red", scene="tag")
    start_game(sim, player)
    player.tap("A")
    (shot,) = player.played
    ends_at = shot.at + player.clip_length(shot.clip)

    sim.advance(ends_at - sim.now - 2 * TICK)
    still_playing = player.is_playing("scene.fire_shot_start")
    sim.advance(2 * TICK)

    assert (still_playing, player.is_playing("scene.fire_shot_start")) == (True, False)


def test_is_playing_rejects_a_clip_the_device_cannot_play(sim):
    player = sim.add_device("red", scene="tag")

    with pytest.raises(ValueError):
        player.is_playing("scene.relaod")


def test_a_looping_clip_is_playing_until_its_effect_stops(sim):
    player = sim.add_device("red", scene="tag", scene_data=ONE_ROUND)
    start_game(sim, player)
    reload_part_way(sim, player)

    looping = player.is_playing("scene.reload")
    player.release("A")

    assert (looping, player.is_playing("scene.reload")) == (True, False)


# ---------------------------------------------------------------------------
# Accelerometer
# ---------------------------------------------------------------------------


def test_a_moving_device_reads_as_motion(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    start_red_light_warning(player)
    reach_red_light(sim, player)

    player.move()
    sim.advance(0.5)

    assert caught_moving(player)


def test_a_still_device_does_not_read_as_motion(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    start_red_light_warning(player)
    reach_red_light(sim, player)

    sim.advance(2.0)

    assert not caught_moving(player)


def test_a_held_tilt_does_not_read_as_motion(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    start_red_light_warning(player)

    player.accelerate(0.0, 4.0, 8.9)
    reach_red_light(sim, player)
    sim.advance(2.0)

    assert not caught_moving(player)


def test_hold_still_stops_a_move(sim):
    player = sim.add_device("p1", scene="red_light_green_light")
    start_red_light_warning(player)
    player.move()

    player.hold_still()
    reach_red_light(sim, player)
    sim.advance(2.0)

    assert not caught_moving(player)
