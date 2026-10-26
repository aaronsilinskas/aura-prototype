"""The red and green warnings, played on a simulated device.

Each warning pulses yellow three times, clicking at every peak, then hands
over to its light. Neither warning judges the player, and both quicken as the
Game Level rises.
"""

from __future__ import annotations

import pytest

from app.simulation import SimulatedDevice
from effects.effect import HapticPattern
from packs.scenes.red_light_green_light.tests.helpers import (
    GAME_OVER_STING,
    GREEN_MUSIC,
    RED_MUSIC,
    SLACK,
    WARNING_PEAK,
    YELLOW,
    last_played_at,
    lit_in,
    survive_round,
    wait_for,
)

HALF_SECOND_PULSES = {
    "rlgl_warning_pulse_max": 0.5,
    "rlgl_warning_pulse_min": 0.5,
    "rlgl_red_duration": 1.0,
}

ONE_SECOND_PULSES = {
    **HALF_SECOND_PULSES,
    "rlgl_warning_pulse_max": 1.0,
    "rlgl_warning_pulse_min": 1.0,
}
"""Peaks far enough apart that one peak's sound ends well before the next."""

QUICKENING = {
    "rlgl_max_level": 2,
    "rlgl_warning_pulse_max": 1.0,
    "rlgl_warning_pulse_min": 0.4,
    "rlgl_red_duration": 1.0,
    "rlgl_green_duration": 1.0,
    "rlgl_level_up_duration": 0.5,
}
"""A 1.0 s pulse at level one, quickening to 0.4 s at the top level, level two."""


def peak_times(player: SimulatedDevice, after: float, before: float) -> list[float]:
    return [p.at for p in player.played if p.clip == WARNING_PEAK and after < p.at < before]


def test_the_red_warning_peaks_three_times_then_red_light_starts(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, RED_MUSIC)

    assert len(peak_times(player, 0.0, last_played_at(player, RED_MUSIC))) == 3


def test_each_warning_peak_clicks_the_haptic(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, RED_MUSIC)

    assert [b.pattern for b in player.buzzed] == [(HapticPattern.STRONG_CLICK,)] * 3


def test_each_warning_peak_sound_plays_once(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=ONE_SECOND_PULSES)
    player.tap("A")
    wait_for(sim, player, WARNING_PEAK)

    sim.advance(player.clip_length(WARNING_PEAK) + SLACK)

    assert not player.is_playing(WARNING_PEAK)


def test_the_red_warning_peaks_in_yellow_on_every_light_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, WARNING_PEAK)

    assert lit_in(player, YELLOW)


def test_the_green_warning_peaks_in_yellow_on_every_light_strip(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)
    player.tap("A")
    wait_for(sim, player, RED_MUSIC)

    wait_for(sim, player, WARNING_PEAK)

    assert lit_in(player, YELLOW)


def test_warning_peaks_come_one_pulse_apart(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, RED_MUSIC)

    first, second, third = peak_times(player, 0.0, sim.now)
    assert (second - first, third - second) == (
        pytest.approx(0.5, abs=SLACK),
        pytest.approx(0.5, abs=SLACK),
    )


def test_warnings_start_at_the_maximum_pulse_at_level_one(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=QUICKENING)

    player.tap("A")
    wait_for(sim, player, RED_MUSIC)

    first, second, _ = peak_times(player, 0.0, sim.now)
    assert second - first == pytest.approx(1.0, abs=SLACK)


def test_warnings_quicken_to_the_minimum_pulse_at_the_top_level(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=QUICKENING)
    player.tap("A")
    survive_round(sim, player)
    round_two = sim.now

    wait_for(sim, player, RED_MUSIC)

    first, second, _ = peak_times(player, round_two, sim.now)
    assert second - first == pytest.approx(0.4, abs=SLACK)


def test_moving_through_the_red_warning_is_not_caught(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    player.move()
    wait_for(sim, player, RED_MUSIC)

    assert not player.has_played(GAME_OVER_STING)


def test_the_green_warning_peaks_three_times_between_red_and_green_light(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, GREEN_MUSIC)

    red, green = last_played_at(player, RED_MUSIC), last_played_at(player, GREEN_MUSIC)
    assert len(peak_times(player, red, green)) == 3


def test_holding_still_through_the_green_warning_is_not_caught(sim):
    player = sim.add_device("p1", scene="red_light_green_light", scene_data=HALF_SECOND_PULSES)

    player.tap("A")
    wait_for(sim, player, GREEN_MUSIC)

    assert not player.has_played(GAME_OVER_STING)
