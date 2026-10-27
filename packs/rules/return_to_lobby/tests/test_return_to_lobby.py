"""``return_to_lobby`` on the Simulation test harness, in every scene that ships it.

A device is launched from ``example_lobby`` into the scene, as a player would,
so its card records where to return to. Each scene keeps its own A and B
handling, which a hold of both must not trip over.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import SimulatedDevice, Simulation

_SCENES_DIR = Path(__file__).resolve().parents[3] / "scenes"

MARGIN = 0.2
"""Covers the debounce, and a press queued behind a tap that just let go of the same button."""


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


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def launch(sim: Simulation, scene: str) -> SimulatedDevice:
    """Switch a device on into the lobby, step its selection to *scene*, and launch it with B."""
    device = sim.add_device("red", scene="example_lobby")
    for _ in range(LOBBY_ENTRIES.index(scene)):
        device.tap("A")
    device.tap("B")
    assert device.scene == scene
    return device


def hold_both(sim: Simulation, device: SimulatedDevice, seconds: float) -> None:
    """Hold A and B together for *seconds*, then let go of both."""
    device.hold("A")
    device.hold("B")
    sim.advance(seconds)
    device.release("A")
    device.release("B")


def test_every_scene_that_ships_the_pack_is_covered():
    assert SCENES == ["element_browser", "hardware_test", "red_light_green_light", "tag"]


@pytest.mark.parametrize("scene", SCENES)
def test_holding_a_and_b_for_hold_seconds_returns_to_the_lobby(sim, scene):
    device = launch(sim, scene)

    hold_both(sim, device, hold_seconds(scene) + MARGIN)

    assert device.scene == "example_lobby"


@pytest.mark.parametrize("scene", SCENES)
def test_a_hold_short_of_hold_seconds_stays_in_the_scene(sim, scene):
    device = launch(sim, scene)

    hold_both(sim, device, hold_seconds(scene) - MARGIN)
    sim.advance(MARGIN)

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_a_hold_released_and_restarted_short_of_hold_seconds_stays_in_the_scene(sim, scene):
    device = launch(sim, scene)
    almost = hold_seconds(scene) - MARGIN

    hold_both(sim, device, almost)
    sim.advance(MARGIN)
    hold_both(sim, device, almost)
    sim.advance(MARGIN)

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_a_device_switched_on_into_the_scene_has_nothing_to_return_to(sim, scene):
    device = sim.add_device("red", scene=scene)

    hold_both(sim, device, hold_seconds(scene) + MARGIN)

    assert device.scene == scene


@pytest.mark.parametrize("scene", SCENES)
def test_a_card_less_device_stays_in_its_scene(sim, scene):
    device = sim.add_device("red", scene=scene, sd_card=False)

    hold_both(sim, device, hold_seconds(scene) + MARGIN)

    assert device.scene == scene
