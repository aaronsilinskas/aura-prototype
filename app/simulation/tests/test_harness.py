"""The Simulation test harness's input and query surface, driven through Tag."""

from __future__ import annotations

import pytest

from app.simulation import SimulatedDevice, Simulation
from engine.network import LINE


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


def test_clip_length_reads_the_clips_wav_header(sim):
    player = sim.add_device("red", scene="tag")

    # fire_shot_start.wav: 3456 frames of 11025 Hz mono
    assert player.clip_length("scene.fire_shot_start") == pytest.approx(3456 / 11025)
