"""``return_to_lobby`` on the Simulation test harness, in every scene that ships it.

A device is launched from ``example_lobby`` into the scene, as a player would,
so its card records where to return to. Each scene keeps its own A and B
handling, which a hold of both must not trip over.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation

_SCENES_DIR = Path(__file__).resolve().parents[3] / "scenes"


def _scene_json(scene: str) -> dict:
    return json.loads((_SCENES_DIR / scene / "scene.json").read_text())


def _scenes_with_the_pack() -> list[str]:
    return sorted(
        path.parent.name
        for path in _SCENES_DIR.glob("*/scene.json")
        if any(pack == "return_to_lobby" for pack, _ in json.loads(path.read_text())["rule_packs"])
    )


SCENES = _scenes_with_the_pack()

LOBBY_ENTRIES = [
    entry["scene"] for entry in _scene_json("example_lobby")["initial_data"]["lobby"]["entries"]
]
"""``example_lobby``'s entries, in the order A steps through them."""


def hold_seconds(scene: str) -> float:
    return _scene_json(scene)["initial_data"]["return_to_lobby"]["hold_seconds"]


def launch(simulation: Simulation, scene: str) -> SimulatedDevice:
    """Switch a device on into the lobby, step its selection to *scene*, and launch it with B."""
    device = simulation.add_device("red", scene="example_lobby")
    for _ in range(LOBBY_ENTRIES.index(scene)):
        device.tap("A")
    device.tap("B")
    assert device.scene == scene
    return device


def test_discovery_finds_every_known_scene_that_ships_the_pack():
    assert set(SCENES) >= {"element_browser", "hardware_test", "red_light_green_light", "tag"}


@pytest.mark.parametrize("scene", SCENES)
def test_holding_a_and_b_for_hold_seconds_returns_to_the_lobby(simulation, scene):
    device = launch(simulation, scene)

    device.hold("A", "B")
    simulation.advance(hold_seconds(scene))

    assert device.scene == "example_lobby"


@pytest.mark.parametrize("scene", SCENES)
def test_a_hold_one_tick_short_of_hold_seconds_stays_in_the_scene(simulation, scene):
    device = launch(simulation, scene)

    device.hold("A", "B")
    simulation.advance(hold_seconds(scene) - TICK)

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_letting_go_part_way_starts_the_hold_over(simulation, scene):
    device = launch(simulation, scene)
    three_quarters = hold_seconds(scene) * 3 / 4  # two of them add up past hold_seconds

    device.hold("A", "B")
    simulation.advance(three_quarters)
    device.release("A", "B")
    device.hold("A", "B")
    simulation.advance(three_quarters)

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_a_device_switched_on_into_the_scene_has_nothing_to_return_to(simulation, scene):
    device = simulation.add_device("red", scene=scene)

    device.hold("A", "B")
    simulation.advance(hold_seconds(scene))

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_a_card_less_device_stays_in_its_scene(simulation, scene):
    device = simulation.add_device("red", scene=scene, sd_card=False)

    device.hold("A", "B")
    simulation.advance(hold_seconds(scene))

    assert device.scene == scene
