"""DeviceHardware — the board-free bundle build_hardware returns. No board imports."""

from __future__ import annotations

from engine.effects.output import EffectOutput
from engine.state import NetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.polled_sensor import PolledSensor
from hardware.shared.radio_transceiver import RadioTransceiver

__all__ = ["DeviceHardware"]


class DeviceHardware:
    """Assembled hardware bundle produced by build_hardware.

    ``ir`` is the single owner of the whole IR subsystem (transmitters,
    receiver, shared transmit gate) — the same ``InfraredTransceiver``
    instance ``HardwareNetworkControls.send_ir`` reaches through. ``None``
    exactly when there is no ``ir`` section declared (or it is disabled).

    ``radio`` is the single owner of the radio subsystem's send and per-tick
    receive — the same ``RadioTransceiver`` instance
    ``HardwareNetworkControls.send_radio`` reaches through. ``None`` on a
    device with no radio peripheral declared; the raw ``RadioTransport`` port
    is private inside the transceiver and never exposed on this bundle.

    ``storage`` is typed as the port (``DeviceStorage``), never the concrete
    ``SdCardStorage`` adapter — ``None`` on a device with no ``sdcard``
    section declared and enabled.

    ``accelerometer`` and ``magnetometer`` are each the
    :class:`~hardware.shared.polled_sensor.PolledSensor` that owns that
    sensor's reading — ``None`` on a device with no such section declared and
    enabled, which is distinct from a failed read.
    """

    __slots__ = (
        "accelerometer",
        "buttons",
        "ir",
        "magnetometer",
        "network_controls",
        "outputs",
        "radio",
        "storage",
    )

    def __init__(
        self,
        outputs: list[EffectOutput],
        buttons: DebouncedButtons,
        accelerometer: PolledSensor | None,
        magnetometer: PolledSensor | None,
        network_controls: NetworkControls,
        ir: InfraredTransceiver | None,
        radio: RadioTransceiver | None,
        storage: DeviceStorage | None,
    ) -> None:
        self.outputs: list[EffectOutput] = outputs
        self.buttons: DebouncedButtons = buttons
        self.accelerometer: PolledSensor | None = accelerometer
        self.magnetometer: PolledSensor | None = magnetometer
        self.network_controls: NetworkControls = network_controls
        self.ir: InfraredTransceiver | None = ir
        self.radio: RadioTransceiver | None = radio
        self.storage: DeviceStorage | None = storage
