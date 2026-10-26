"""Booting into Tag and starting a game, played on simulated devices.

A device boots into Ready, a button press starts the countdown, and the
countdown runs into Playing. A test that depends on a tunable pins it with
``scene_data``.
"""

from __future__ import annotations

import pytest

from app.simulation import Simulation, Strip
from effects.effect import HapticPattern
from engine.state import Scope

AMMO_AMBER = 0xFFBF00
GREEN = 0x00FF00

EVERY_STRIP = [
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.Global.MAIN,
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
]

BAR_FREE_STRIPS = [Scope.Global.DEBUFF, Scope.Global.MAIN, Scope.DIRECTIONAL, Scope.AMBIENT]
"""The strips Playing shows no bar on."""


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def sweeping_red(strip: Strip) -> bool:
    """Part of the strip lit, and only in red: the Ready laser sweep."""
    return 0 < strip.lit < strip.size and all(p & 0x00FFFF == 0 for p in strip.pixels)


def peaks_before_go(clips: list[str]) -> int:
    return clips[: clips.index("scene.go_start")].count("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Ready
# ---------------------------------------------------------------------------


def test_a_booted_device_sweeps_red_across_every_strip(sim):
    player = sim.add_device("red", scene="tag")

    sim.advance(0.5)

    assert all(sweeping_red(player.strip(scope)) for scope in EVERY_STRIP)


def test_a_booted_device_plays_the_ready_shots_once(sim):
    player = sim.add_device("red", scene="tag")

    sim.advance(10.0)

    assert [p.clip for p in player.played] == ["scene.ready_shots_start"]


@pytest.mark.parametrize("button", ["A", "B"])
def test_pressing_either_button_in_ready_starts_the_countdown(sim, button):
    player = sim.add_device("red", scene="tag", scene_data={"tag_warning_pulse_duration": 0.6})
    sim.advance(0.5)

    player.tap(button)
    sim.advance(0.6)

    assert player.has_played("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Countdown
# ---------------------------------------------------------------------------


def test_each_countdown_pulse_clicks_the_haptic(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_warning_pulse_duration": 0.6})

    player.tap("A")
    sim.advance(0.6)

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.SHARP_CLICK,)]


def test_the_countdown_pulses_every_strip(sim):
    player = sim.add_device("red", scene="tag", scene_data={"tag_warning_pulse_duration": 0.6})

    player.tap("A")
    sim.advance(0.6)

    assert all(not player.strip(scope).dark for scope in EVERY_STRIP)


@pytest.mark.parametrize("count", [3, 7])
def test_the_countdown_runs_its_pulse_count_then_the_game_starts(sim, count):
    countdown = {"tag_warning_pulse_count": count, "tag_warning_pulse_duration": 0.4}
    player = sim.add_device("red", scene="tag", scene_data=countdown)

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))

    assert peaks_before_go([p.clip for p in player.played]) == count


# ---------------------------------------------------------------------------
# Playing begins
# ---------------------------------------------------------------------------


def test_the_game_starts_with_the_go_sound_and_a_strong_buzz(sim):
    player = sim.add_device("red", scene="tag")

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))

    assert player.buzzed[-1].pattern == (HapticPattern.STRONG_BUZZ,)


def test_the_game_starts_with_a_full_green_hitpoints_bar(sim):
    player = sim.add_device("red", scene="tag")

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))

    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_the_game_starts_with_a_full_amber_ammo_bar(sim):
    player = sim.add_device("red", scene="tag")

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))

    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_the_countdown_pulse_stops_when_the_game_starts(sim):
    player = sim.add_device("red", scene="tag")

    player.tap("A")
    sim.run_until(lambda: player.has_played("scene.go_start"))

    assert all(player.strip(scope).dark for scope in BAR_FREE_STRIPS)
