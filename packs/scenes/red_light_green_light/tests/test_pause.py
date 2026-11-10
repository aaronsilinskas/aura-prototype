"""Red Light Green Light paused by an Overlay, played on a simulated device.

A pause stops the game's time: a phase paused partway keeps the rest of its
duration for after the pause, however long the pause lasts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import SimulatedDevice, Simulation
from packs.scenes.red_light_green_light.tests.helpers import (
    GREEN_MUSIC,
    QUICK_WARNINGS,
    RED_MUSIC,
    SLACK,
    WARNING_PEAK,
    last_played_at,
    overrides,
    wait_for,
)

RED_LIGHT = {**QUICK_WARNINGS, "red_duration_max": 3.0, "max_level": 5}
"""A three-second Red Light, followed by a 0.6 s green warning."""

GREEN_WARNING = 0.6
"""How long the green warning between Red Light and Green Light lasts under ``QUICK_WARNINGS``."""

TWO_TIMED_CHANGES_SLACK = 3 * SLACK
"""How far Red Light's end, read off Green Light's start, may trail its duration.

Red Light's end and the green warning's end each trail their Setting by up to
``SLACK``, and either can land a tick later still on a tick boundary.
"""

PLAYED_BEFORE_PAUSE = 1.0
PAUSE = 5.0
"""Longer than all of Red Light, so a pause that used up its time would end it."""


@pytest.fixture()
def card(tmp_path: Path) -> Path:
    """A card carrying ``pause``: a scene with no rules and no effects."""
    scene_dir = tmp_path / "aura_packs" / "scenes" / "pause"
    scene_dir.mkdir(parents=True)
    for package in (tmp_path / "aura_packs", tmp_path / "aura_packs" / "scenes", scene_dir):
        (package / "__init__.py").touch()
    (scene_dir / "scene.json").write_text(
        json.dumps({"version": "1.0", "effect_packs": [], "rule_packs": []})
    )
    return tmp_path


def pause_red_light_partway(
    simulation: Simulation, player: SimulatedDevice
) -> tuple[float, float, float]:
    """Reach Red Light, pause it after ``PLAYED_BEFORE_PAUSE`` for ``PAUSE``, and unpause.

    Returns when Red Light started, and when the overlay and the pop were asked for.
    """
    player.hold_still()
    player.tap("A")
    wait_for(simulation, player, RED_MUSIC)
    red_light_started_at = last_played_at(player, RED_MUSIC)
    simulation.advance(PLAYED_BEFORE_PAUSE)
    paused_at = simulation.now
    player.overlay("pause")
    simulation.advance(PAUSE)
    unpaused_at = simulation.now
    player.pop()
    return red_light_started_at, paused_at, unpaused_at


def test_a_paused_red_light_does_not_end_during_the_pause(simulation, card):
    player = simulation.add_device(
        "p1", scene="red_light_green_light", card=card, setting_overrides=overrides(RED_LIGHT)
    )
    red_light_started_at, _, _ = pause_red_light_partway(simulation, player)

    simulation.advance(0.5)

    assert last_played_at(player, WARNING_PEAK) < red_light_started_at, (
        "the green warning must not have started"
    )


def test_a_paused_red_light_ends_after_the_rest_of_its_duration_once_unpaused(simulation, card):
    player = simulation.add_device(
        "p1", scene="red_light_green_light", card=card, setting_overrides=overrides(RED_LIGHT)
    )
    red_light_started_at, paused_at, unpaused_at = pause_red_light_partway(simulation, player)

    wait_for(simulation, player, GREEN_MUSIC)

    red_light_ended_at = last_played_at(player, GREEN_MUSIC) - GREEN_WARNING
    red_light_played_for = (red_light_ended_at - red_light_started_at) - (unpaused_at - paused_at)
    assert red_light_played_for == pytest.approx(3.0, abs=TWO_TIMED_CHANGES_SLACK)
