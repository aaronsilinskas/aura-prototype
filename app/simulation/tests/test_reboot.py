"""A Simulated device reboots as a real reset does: through its card, into the next scene.

Driven through ``example_lobby``, whose B reboots into the selected scene, and
``return_to_lobby``, whose A+B hold reboots back to the scene that launched
this one. ``return_to_lobby``'s own behaviour is pinned in its pack's tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.network import LINE
from engine.state import Scope

_SCENES_DIR = Path(__file__).resolve().parents[3] / "packs" / "scenes"


def _initial_data(scene: str) -> dict:
    return json.loads((_SCENES_DIR / scene / "scene.json").read_text())["initial_data"]


LOBBY_ENTRIES = [entry["scene"] for entry in _initial_data("example_lobby")["lobby"]["entries"]]
"""``example_lobby``'s entries, in the order A steps through them."""


def start_game(simulation: Simulation, *players: SimulatedDevice) -> None:
    """Start a Tag game on every player: A in Ready, then the countdown."""
    for player in players:
        player.tap("A")
    simulation.run_until(lambda: all(p.has_played("scene.go_start") for p in players))


def launch(device: SimulatedDevice, scene: str) -> None:
    """Step the lobby's selection to *scene*, then launch it with B."""
    for _ in range(LOBBY_ENTRIES.index(scene)):
        device.tap("A")
    device.tap("B")


def hold_to_return(simulation: Simulation, device: SimulatedDevice) -> None:
    """Hold A+B for the scene's ``hold_seconds``, rebooting back to the lobby; A and B stay down."""
    device.hold("A", "B")
    simulation.advance(_initial_data(device.scene)["return_to_lobby"]["hold_seconds"])


def test_the_lobbys_b_reboots_into_the_selected_scene(simulation):
    device = simulation.add_device("red", scene="example_lobby")

    launch(device, "element_browser")

    assert device.scene == "element_browser"


def test_a_card_less_device_stays_in_its_scene(simulation):
    device = simulation.add_device("red", scene="example_lobby", sd_card=False)

    launch(device, "element_browser")

    assert device.scene == "example_lobby"


def test_after_a_reboot_into_tag_the_device_speaks_tags_wire_frame(simulation):
    red = simulation.add_device("red", scene="example_lobby")
    blue = simulation.add_device("blue", scene="tag")
    launch(red, "tag")
    start_game(simulation, red, blue)

    blue.aim(LINE, at=red)
    blue.tap("A")
    simulation.advance(0.1)

    assert red.has_played("scene.hit_start")


def test_recordings_made_before_a_reboot_are_kept(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "tag")
    simulation.run_until(lambda: device.has_played("scene.ready_shots_start"))

    hold_to_return(simulation, device)

    assert device.scene == "example_lobby"
    assert device.has_played("scene.ready_shots_start")


def test_a_reboot_leaves_strips_dark_until_the_new_scene_lights_them(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    simulation.advance(TICK)
    assert not device.strip(Scope.AMBIENT).dark  # the lobby previews a scene there

    launch(device, "element_browser")

    assert device.strip(Scope.AMBIENT).dark  # the browser never lights ambient


def test_a_button_held_through_a_reboot_gives_no_new_press(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    hold_to_return(simulation, device)  # A is still down as the lobby boots
    device.release("A", "B")
    device.tap("B")

    assert device.scene == LOBBY_ENTRIES[0]  # the lobby's A never stepped the selection


def test_a_rule_failure_inside_a_tick_still_fails(simulation):
    simulation.add_device("red", scene="example_lobby", scene_data={"lobby": {"entries": []}})

    with pytest.raises(ValueError, match="scopes"):
        simulation.advance(TICK)


def test_after_a_reboot_the_device_still_sends_radio_as_its_own_node(simulation, capsys):
    # hardware_test's radio mode, four presses of B in, logs each packet's sender.
    blue = simulation.add_device("blue", scene="hardware_test")
    red = simulation.add_device("red", scene="example_lobby")
    launch(red, "hardware_test")
    for device in (blue, red):
        for _ in range(4):
            device.tap("B")
    capsys.readouterr()

    red.tap("A")

    assert f"from {red.radio_node}" in capsys.readouterr().out


def test_a_magnetized_field_holds_through_a_reboot(simulation):
    # hardware_test's magnetometer mode, two presses of B in, fills the
    # personal strip red at a 100 µT field on x.
    device = simulation.add_device("red", scene="example_lobby")
    device.magnetize(100.0, 0.0, 0.0)

    launch(device, "hardware_test")
    for _ in range(2):
        device.tap("B")

    assert device.strip(Scope.PERSONAL).all_lit(0xFF0000)


def test_a_card_less_device_redeployed_with_a_scene_boots_it(simulation):
    device = simulation.add_device("red", scene="example_lobby", sd_card=False)

    device.redeploy(scene="element_browser")

    assert device.scene == "element_browser"


def test_a_redeployed_scene_outranks_a_persisted_scene(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    device.redeploy(scene="hardware_test")

    assert device.scene == "hardware_test"


def test_an_on_device_reboot_after_a_redeploy_persists(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")
    device.redeploy(scene="example_lobby")

    launch(device, "tag")

    assert device.scene == "tag"


def test_redeploying_the_same_scene_after_navigating_away_boots_it_again(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    device.redeploy(scene="example_lobby")
    launch(device, "element_browser")

    device.redeploy(scene="example_lobby")

    assert device.scene == "example_lobby"


def test_returning_right_after_a_redeploy_stays_in_the_deployed_scene(simulation):
    # Launching tag from the lobby records the lobby to return to; the
    # redeploy clears that, so A+B in the deployed scene has nowhere to go.
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "tag")
    device.redeploy(scene="hardware_test")

    hold_to_return(simulation, device)

    assert device.scene == "hardware_test"


def test_a_redeploy_over_a_malformed_card_state_boots_the_deployed_scene(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")
    (device.card / "aura-state.json").write_text("{not valid json")

    device.redeploy(scene="hardware_test")

    assert device.scene == "hardware_test"


def test_redeploying_an_unknown_scene_over_a_persisted_scene_fails_naming_the_known_scenes(
    simulation,
):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    with pytest.raises(ValueError, match="unknown scene 'no_such_scene'; known scenes: "):
        device.redeploy(scene="no_such_scene")


def test_a_valid_redeploy_after_an_unknown_scene_boots_it(simulation):
    device = simulation.add_device("red", scene="example_lobby")
    launch(device, "element_browser")
    with pytest.raises(ValueError):
        device.redeploy(scene="no_such_scene")

    device.redeploy(scene="hardware_test")

    assert device.scene == "hardware_test"


def test_a_reset_after_navigating_away_from_a_redeployed_scene_keeps_the_navigated_scene(
    simulation,
):
    device = simulation.add_device("red", scene="example_lobby")
    device.redeploy(scene="example_lobby")
    launch(device, "element_browser")

    device.reset()

    assert device.scene == "element_browser"
