"""A Simulated device that lacks some Capabilities: ``add_device(without=...)``.

Booted into hardware_test, which requires nothing of its own, so a device
lacking any hardware still boots it; boot itself runs only a scene the
device has the Required capabilities for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.simulation import Simulation
from engine.capabilities import MissingCapabilityError
from engine.pack_catalog import scan_pack_roots

_FULL = frozenset(
    (
        "button.A",
        "button.B",
        "accelerometer",
        "magnetometer",
        "radio",
        "storage",
        "ir.line",
        "ir.cone",
        "ir.area_of_effect",
        "ir.receive",
    )
)
_IR = frozenset(("ir.line", "ir.cone", "ir.area_of_effect", "ir.receive"))
RADIO_MODE = 4
"""Presses of B from switch-on that reach hardware_test's radio mode, where A sends."""


def test_a_fully_built_simulated_device_has_every_capability(simulation):
    device = simulation.add_device("red", scene="hardware_test")

    assert device.capabilities == _FULL


@pytest.mark.parametrize(
    ("without", "lost"),
    [
        ("button.A", {"button.A", "button.B"}),
        ("button.B", {"button.B"}),
        ("button.C", set()),
        ("accelerometer", {"accelerometer"}),
        ("magnetometer", {"magnetometer"}),
        ("radio", {"radio"}),
        ("storage", {"storage"}),
        ("ir.line", {"ir.line"}),
        ("ir.cone", {"ir.cone"}),
        ("ir.area_of_effect", {"ir.area_of_effect"}),
        ("ir.receive", {"ir.receive"}),
    ],
)
def test_without_a_capability_the_device_lacks_it_and_keeps_the_rest(simulation, without, lost):
    device = simulation.add_device("red", scene="hardware_test", without={without})

    assert device.capabilities == _FULL - lost


def test_without_every_ir_item_the_device_has_no_ir(simulation):
    device = simulation.add_device("red", scene="hardware_test", without=_IR)

    assert device.capabilities == _FULL - _IR


def test_without_a_name_outside_the_vocabulary_raises(simulation):
    with pytest.raises(ValueError, match="laser"):
        simulation.add_device("red", scene="hardware_test", without={"laser"})


def test_without_storage_the_device_has_no_card(simulation):
    device = simulation.add_device("red", scene="hardware_test", without={"storage"})

    assert device.card is None


def test_a_card_handed_to_a_device_without_storage_raises(simulation, tmp_path):
    with pytest.raises(ValueError, match="no SD card"):
        simulation.add_device("red", scene="hardware_test", without={"storage"}, card=tmp_path)


def test_a_device_without_a_radio_ignores_packets_others_send(simulation: Simulation):
    sender = simulation.add_device("red", scene="hardware_test")
    simulation.add_device("blue", scene="hardware_test", without={"radio"})
    for _ in range(RADIO_MODE):
        sender.tap("B")

    sender.tap("A")
    simulation.advance(0.1)

    assert len(sender.radio_sent) == 1


def test_pressing_a_button_the_device_lacks_raises_naming_it(simulation):
    device = simulation.add_device("red", scene="hardware_test", without={"button.B"})

    with pytest.raises(ValueError, match="'B'"):
        device.tap("B")


# ---------------------------------------------------------------------------
# Boot runs only a scene the device can run (issue #1164)
# ---------------------------------------------------------------------------


def _persist(card: Path, scene: str) -> None:
    (card / "aura-state.json").write_text(json.dumps({"scene": scene}))


@pytest.mark.parametrize("scene", sorted(scan_pack_roots(["packs"]).scene_registry.names()))
def test_a_fully_built_device_boots_every_shipped_scene(simulation, scene):
    device = simulation.add_device("red", scene=scene)

    assert device.scene == scene


def test_a_persisted_scene_the_device_cannot_run_boots_the_default_scene(simulation, tmp_path):
    _persist(tmp_path, "red_light_green_light")

    device = simulation.add_device(
        "red", scene="hardware_test", card=tmp_path, without={"accelerometer"}
    )

    assert device.scene == "hardware_test"


def test_a_persisted_scene_the_device_cannot_run_is_left_on_the_card(simulation, tmp_path):
    _persist(tmp_path, "red_light_green_light")

    simulation.add_device("red", scene="hardware_test", card=tmp_path, without={"accelerometer"})

    state = json.loads((tmp_path / "aura-state.json").read_text())
    assert state["scene"] == "red_light_green_light"


def test_boot_raises_when_neither_the_persisted_nor_the_default_scene_fits(simulation, tmp_path):
    _persist(tmp_path, "red_light_green_light")

    with pytest.raises(MissingCapabilityError) as excinfo:
        simulation.add_device(
            "red", scene="tag", card=tmp_path, without={"accelerometer", "ir.line"}
        )

    assert (excinfo.value.scene, excinfo.value.capabilities) == ("tag", {"ir.line"})
