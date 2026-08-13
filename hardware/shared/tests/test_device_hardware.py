"""Behaviour-driven tests for hardware/shared/device_hardware.py."""

import pytest

from hardware.shared.device_hardware import DeviceHardware


def test_device_hardware_is_constructible_under_cpython_with_plain_fakes():
    """DeviceHardware pulls no board module, so plain fakes suffice — no CircuitPython stubs."""
    outputs = ["fake-output"]
    buttons = "fake-buttons"
    accelerometer = "fake-accelerometer"
    network_controls = "fake-network-controls"
    transmit_pump = "fake-transmit-pump"
    ir_receiver = "fake-ir-receiver"
    radio = "fake-radio"
    storage = "fake-storage"
    audio_registry = "fake-audio-registry"

    hardware = DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        network_controls=network_controls,
        transmit_pump=transmit_pump,
        ir_receiver=ir_receiver,
        radio=radio,
        storage=storage,
        audio_registry=audio_registry,
    )

    assert hardware.outputs is outputs
    assert hardware.buttons is buttons
    assert hardware.accelerometer is accelerometer
    assert hardware.network_controls is network_controls
    assert hardware.transmit_pump is transmit_pump
    assert hardware.ir_receiver is ir_receiver
    assert hardware.radio is radio
    assert hardware.storage is storage
    assert hardware.audio_registry is audio_registry


def test_device_hardware_radio_defaults_to_none_when_no_radio_peripheral_is_wired():
    hardware = DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump="fake-transmit-pump",
        ir_receiver=None,
        radio=None,
        storage=None,
        audio_registry=None,
    )

    assert hardware.radio is None


def test_device_hardware_storage_defaults_to_none_when_no_sdcard_is_wired():
    hardware = DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump="fake-transmit-pump",
        ir_receiver=None,
        radio=None,
        storage=None,
        audio_registry=None,
    )

    assert hardware.storage is None


def test_device_hardware_audio_registry_defaults_to_none_when_no_audio_is_wired():
    hardware = DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump="fake-transmit-pump",
        ir_receiver=None,
        radio=None,
        storage=None,
        audio_registry=None,
    )

    assert hardware.audio_registry is None


def test_device_hardware_rejects_attributes_outside_its_slots():
    hardware = DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        network_controls="fake-network-controls",
        transmit_pump="fake-transmit-pump",
        ir_receiver=None,
        radio=None,
        storage=None,
        audio_registry=None,
    )

    with pytest.raises(AttributeError):
        hardware.gate = "not-a-real-field"
