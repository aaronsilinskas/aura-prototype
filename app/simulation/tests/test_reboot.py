"""A Simulated device reboots as a real reset does: through its card, into the next scene.

Driven through ``example_lobby``, whose B reboots into the selected scene, and
``return_to_lobby``, whose A+B hold reboots back to the scene that launched
this one.
"""

from __future__ import annotations

import pytest

from app.simulation import TICK, SimulatedDevice, Simulation
from engine.network import LINE
from engine.state import Scope

HOLD_SECONDS = 5.0
"""``return_to_lobby``'s ``hold_seconds`` in every scene that ships it."""

LOBBY_ENTRIES = ["hardware_test", "element_browser", "red_light_green_light", "tag"]
"""``example_lobby``'s entries, in the order A steps through them."""


@pytest.fixture()
def sim() -> Simulation:
    return Simulation()


def start_game(sim: Simulation, *players: SimulatedDevice) -> None:
    """Start a Tag game on every player: A in Ready, then the countdown."""
    for player in players:
        player.tap("A")
    sim.run_until(lambda: all(p.has_played("scene.go_start") for p in players))


def launch(device: SimulatedDevice, scene: str) -> None:
    """Step the lobby's selection to *scene*, then launch it with B."""
    for _ in range(LOBBY_ENTRIES.index(scene)):
        device.tap("A")
    device.tap("B")


def hold_to_return(sim: Simulation, device: SimulatedDevice) -> None:
    """Hold A+B for the full ``hold_seconds``, then let go.

    The margin covers the debounce, and a press queued behind a tap that
    just let go of the same button.
    """
    device.hold("A")
    device.hold("B")
    sim.advance(HOLD_SECONDS + 0.2)
    device.release("A")
    device.release("B")


def test_the_lobbys_b_reboots_into_the_selected_scene(sim):
    device = sim.add_device("red", scene="example_lobby")

    launch(device, "element_browser")

    assert device.scene == "element_browser"


def test_holding_a_and_b_for_hold_seconds_reboots_back_to_the_lobby(sim):
    device = sim.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    hold_to_return(sim, device)

    assert device.scene == "example_lobby"


def test_holding_a_and_b_short_of_hold_seconds_stays_in_the_scene(sim):
    device = sim.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    device.hold("A")
    device.hold("B")
    sim.advance(HOLD_SECONDS - 0.5)

    assert device.scene == "element_browser"


def test_a_card_less_device_stays_in_its_scene(sim):
    device = sim.add_device("red", scene="example_lobby", sd_card=False)

    launch(device, "element_browser")

    assert device.scene == "example_lobby"


def test_a_device_switched_on_into_a_scene_has_nothing_to_return_to(sim):
    device = sim.add_device("red", scene="element_browser")

    hold_to_return(sim, device)

    assert device.scene == "element_browser"


def test_after_a_reboot_into_tag_the_device_speaks_tags_wire_frame(sim):
    red = sim.add_device("red", scene="example_lobby")
    blue = sim.add_device("blue", scene="tag")
    launch(red, "tag")
    start_game(sim, red, blue)

    blue.aim(LINE, at=red)
    blue.tap("A")
    sim.advance(0.1)

    assert red.has_played("scene.hit_start")


def test_recordings_made_before_a_reboot_are_kept(sim):
    device = sim.add_device("red", scene="example_lobby")
    launch(device, "tag")
    sim.run_until(lambda: device.has_played("scene.ready_shots_start"))

    hold_to_return(sim, device)

    assert device.scene == "example_lobby"
    assert device.has_played("scene.ready_shots_start")


def test_a_reboot_leaves_strips_dark_until_the_new_scene_lights_them(sim):
    device = sim.add_device("red", scene="example_lobby")
    sim.advance(TICK)
    assert not device.strip(Scope.AMBIENT).dark  # the lobby previews a scene there

    launch(device, "element_browser")

    assert device.strip(Scope.AMBIENT).dark  # the browser never lights ambient


def test_a_button_held_through_a_reboot_gives_no_new_press(sim):
    device = sim.add_device("red", scene="example_lobby")
    launch(device, "element_browser")

    hold_to_return(sim, device)  # A is still down as the lobby boots
    sim.advance(0.2)
    device.tap("B")

    assert device.scene == LOBBY_ENTRIES[0]  # the lobby's A never stepped the selection


def test_a_rule_failure_inside_a_tick_still_fails(sim):
    sim.add_device("red", scene="example_lobby", scene_data={"lobby": {"entries": []}})

    with pytest.raises(ValueError, match="scopes"):
        sim.advance(TICK)
