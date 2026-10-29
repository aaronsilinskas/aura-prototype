"""Booting into Tag and starting a game, played on simulated devices.

A device boots into Ready, a button press starts the countdown, and the
countdown runs into Playing.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, Strip
from effects.effect import HapticPattern
from engine.state import Scope
from packs.scenes.tag.tests.helpers import AMMO_AMBER, EVERY_STRIP, GREEN, sweeping_red

BAR_FREE_STRIPS = [Scope.Global.DEBUFF, Scope.Global.MAIN, Scope.DIRECTIONAL, Scope.AMBIENT]
"""The strips Playing shows no bar on."""

ONE_PULSE = {"tag_warning_pulse_duration": 0.6}


def lit_positions(strip: Strip) -> set[int]:
    return {i for i, p in enumerate(strip.pixels) if p != 0}


def peaks_before_go(clips: list[str]) -> int:
    return clips[: clips.index("scene.go_start")].count("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Ready
# ---------------------------------------------------------------------------


def test_a_booted_device_sweeps_red_across_every_strip(simulation):
    player = simulation.add_device("red", scene="tag")

    simulation.advance(TICK)

    assert all(sweeping_red(player.strip(scope)) for scope in EVERY_STRIP)


def test_the_ready_laser_moves_along_the_strip(simulation):
    player = simulation.add_device("red", scene="tag")
    simulation.advance(TICK)
    before = lit_positions(player.strip(Scope.Global.MAIN))

    simulation.advance(0.25)

    after = player.strip(Scope.Global.MAIN)
    assert sweeping_red(after)
    assert lit_positions(after) != before


def test_an_idle_device_plays_the_ready_shots_only_once(simulation):
    player = simulation.add_device("red", scene="tag")

    simulation.advance(10.0)

    assert [p.clip for p in player.played] == ["scene.ready_shots_start"]


@pytest.mark.parametrize("button", ["A", "B"])
def test_pressing_either_button_in_ready_starts_the_countdown(simulation, button):
    player = simulation.add_device("red", scene="tag", scene_data=ONE_PULSE)

    player.tap(button)
    simulation.advance(ONE_PULSE["tag_warning_pulse_duration"])

    assert player.has_played("scene.warning_pulse_peak")


# ---------------------------------------------------------------------------
# Countdown
# ---------------------------------------------------------------------------


def test_each_countdown_pulse_clicks_the_haptic(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=ONE_PULSE)

    player.tap("A")
    simulation.advance(ONE_PULSE["tag_warning_pulse_duration"])

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.SHARP_CLICK,)]


def test_the_countdown_pulses_every_strip(simulation):
    player = simulation.add_device("red", scene="tag", scene_data=ONE_PULSE)

    player.tap("A")
    simulation.advance(ONE_PULSE["tag_warning_pulse_duration"])

    assert all(not player.strip(scope).dark for scope in EVERY_STRIP)


@pytest.mark.parametrize("count", [3, 7])
def test_the_countdown_runs_its_pulse_count_then_the_game_starts(simulation, count):
    countdown = {"tag_warning_pulse_count": count, "tag_warning_pulse_duration": 0.4}
    player = simulation.add_device("red", scene="tag", scene_data=countdown)

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert peaks_before_go([p.clip for p in player.played]) == count


def test_pressing_during_the_countdown_does_not_restart_it(simulation):
    countdown = {"tag_warning_pulse_count": 3, "tag_warning_pulse_duration": 0.4}
    player = simulation.add_device("red", scene="tag", scene_data=countdown)
    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.warning_pulse_peak"))

    player.tap("A")
    player.tap("B")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert peaks_before_go([p.clip for p in player.played]) == 3


# ---------------------------------------------------------------------------
# Playing begins
# ---------------------------------------------------------------------------


def test_the_game_starts_with_the_go_sound_and_a_strong_buzz(simulation):
    player = simulation.add_device("red", scene="tag")

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert player.buzzed[-1].pattern == (HapticPattern.STRONG_BUZZ,)


def test_the_game_starts_with_a_full_green_hitpoints_bar(simulation):
    player = simulation.add_device("red", scene="tag")

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert player.strip(Scope.PERSONAL).all_lit(GREEN)


def test_the_game_starts_with_a_full_amber_ammo_bar(simulation):
    player = simulation.add_device("red", scene="tag")

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert player.strip(Scope.Global.BUFF).all_lit(AMMO_AMBER)


def test_the_countdown_pulse_stops_when_the_game_starts(simulation):
    player = simulation.add_device("red", scene="tag")

    player.tap("A")
    simulation.run_until(lambda: player.has_played("scene.go_start"))

    assert all(player.strip(scope).dark for scope in BAR_FREE_STRIPS)
