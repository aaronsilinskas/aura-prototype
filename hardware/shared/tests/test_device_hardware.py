"""Behaviour-driven tests for hardware/shared/device_hardware.py."""

import pytest

from engine.effects.output import EffectOutput
from engine.input import AccelerationData, MagneticData
from engine.log import Logger
from engine.state import NetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import IrTransmitGate
from hardware.shared.polled_sensor import PolledSensor
from hardware.shared.radio_transceiver import RadioTransceiver


def _still() -> tuple[float, float, float]:
    return (0.0, 0.0, 0.0)


def test_device_hardware_is_constructible_under_cpython_with_board_free_parts(tmp_path):
    """DeviceHardware pulls no board module, so board-free parts suffice: no CircuitPython stubs."""
    outputs = [EffectOutput()]
    buttons = DebouncedButtons([])
    accelerometer = PolledSensor(_still, AccelerationData(), "accelerometer", Logger("[hw]"))
    magnetometer = PolledSensor(_still, MagneticData(), "magnetometer", Logger("[hw]"))
    network_controls = NetworkControls()
    ir = InfraredTransceiver({}, None, IrTransmitGate())
    radio = RadioTransceiver(None)
    storage = DeviceStorage(str(tmp_path))
    polled = (buttons, ir)

    hardware = DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=network_controls,
        ir=ir,
        radio=radio,
        storage=storage,
        capabilities=frozenset(),
        polled=polled,
    )

    assert hardware.outputs is outputs
    assert hardware.buttons is buttons
    assert hardware.accelerometer is accelerometer
    assert hardware.magnetometer is magnetometer
    assert hardware.network_controls is network_controls
    assert hardware.ir is ir
    assert hardware.radio is radio
    assert hardware.storage is storage
    assert hardware.polled is polled


def test_device_hardware_rejects_attributes_outside_its_slots():
    hardware = DeviceHardware(
        outputs=[],
        buttons=DebouncedButtons([]),
        accelerometer=None,
        magnetometer=None,
        network_controls=NetworkControls(),
        ir=None,
        radio=None,
        storage=None,
        capabilities=frozenset(),
        polled=(),
    )

    with pytest.raises(AttributeError):
        hardware.gate = "not-a-real-field"  # type: ignore[attr-defined]  # proves __slots__ rejects it
