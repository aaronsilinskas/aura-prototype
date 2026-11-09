"""A Simulated device that lacks some Capabilities: ``add_device(without=...)``.

Booted into hardware_test, which requires nothing of its own, so a device
lacking any hardware still boots it.
"""

from __future__ import annotations

import pytest

from app.simulation import Simulation

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
