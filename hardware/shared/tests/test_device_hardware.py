"""Behaviour-driven tests for hardware/shared/device_hardware.py."""

import pytest

from hardware.shared.device_hardware import DeviceHardware


def test_device_hardware_is_constructible_under_cpython_with_plain_fakes():
    """DeviceHardware pulls no board module, so plain fakes suffice — no CircuitPython stubs."""
    outputs = ["fake-output"]
    buttons = "fake-buttons"
    accelerometer = "fake-accelerometer"
    magnetometer = "fake-magnetometer"
    network_controls = "fake-network-controls"
    ir = "fake-ir"
    radio = "fake-radio"
    storage = "fake-storage"
    audio_registry = "fake-audio-registry"

    hardware = DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=network_controls,
        ir=ir,
        radio=radio,
        storage=storage,
        audio_registry=audio_registry,
    )

    assert hardware.outputs is outputs
    assert hardware.buttons is buttons
    assert hardware.accelerometer is accelerometer
    assert hardware.magnetometer is magnetometer
    assert hardware.network_controls is network_controls
    assert hardware.ir is ir
    assert hardware.radio is radio
    assert hardware.storage is storage
    assert hardware.audio_registry is audio_registry


def test_device_hardware_rejects_attributes_outside_its_slots():
    hardware = DeviceHardware(
        outputs=[],
        buttons="fake-buttons",
        accelerometer=None,
        magnetometer=None,
        network_controls="fake-network-controls",
        ir=None,
        radio=None,
        storage=None,
        audio_registry=None,
    )

    with pytest.raises(AttributeError):
        hardware.gate = "not-a-real-field"
