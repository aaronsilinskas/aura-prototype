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

    hardware = DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=network_controls,
        ir=ir,
        radio=radio,
        storage=storage,
    )

    assert hardware.outputs is outputs
    assert hardware.buttons is buttons
    assert hardware.accelerometer is accelerometer
    assert hardware.magnetometer is magnetometer
    assert hardware.network_controls is network_controls
    assert hardware.ir is ir
    assert hardware.radio is radio
    assert hardware.storage is storage


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
    )

    with pytest.raises(AttributeError):
        hardware.gate = "not-a-real-field"
