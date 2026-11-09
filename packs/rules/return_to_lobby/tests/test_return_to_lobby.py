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
from engine.capabilities import MissingCapabilityError
from packs.tests.settings_helper import settings_for

_SCENES_DIR = Path(__file__).resolve().parents[3] / "scenes"


def _scenes_with_the_pack() -> list[str]:
    return sorted(
        path.parent.name
        for path in _SCENES_DIR.glob("*/scene.json")
        if any(
            pack["name"] == "return_to_lobby" for pack in json.loads(path.read_text())["rule_packs"]
        )
    )


SCENES = _scenes_with_the_pack()

LOBBY_ENTRIES = [
    entry["scene"]
    for entry in settings_for("example_lobby").get("lobby", "entries")  # type: ignore[attr-defined]
]
"""``example_lobby``'s entries, in the order A steps through them."""


def hold_seconds(scene: str) -> float:
    return settings_for(scene).get_float("return_to_lobby", "hold_seconds")


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


@pytest.mark.parametrize("lacking", ["button.B", "storage"])
@pytest.mark.parametrize("scene", SCENES)
def test_a_device_lacking_what_the_pack_requires_does_not_start_the_scene(
    simulation, scene, lacking
):
    with pytest.raises(MissingCapabilityError) as excinfo:
        simulation.add_device("red", scene=scene, without={lacking})

    assert lacking in excinfo.value.capabilities


def test_a_hold_does_not_return_to_a_scene_the_device_cannot_run(simulation, tmp_path):
    state_file = tmp_path / "aura-state.json"
    state_file.write_text(json.dumps({"return_to": "red_light_green_light"}))
    device = simulation.add_device(
        "red", scene="element_browser", card=tmp_path, without={"accelerometer"}
    )

    device.hold("A", "B")
    with pytest.raises(MissingCapabilityError) as excinfo:
        simulation.advance(hold_seconds("element_browser"))

    assert excinfo.value.scene == "red_light_green_light"
    assert json.loads(state_file.read_text()) == {"return_to": "red_light_green_light"}
