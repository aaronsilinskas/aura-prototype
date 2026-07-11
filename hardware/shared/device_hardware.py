"""DeviceHardware — the board-free bundle build_hardware returns. No board imports."""

from __future__ import annotations

from engine.effects.output import EffectOutput
from engine.network import TransmitPump
from engine.state import NetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.ir_transport import InfraredReceiver

__all__ = ["DeviceHardware"]


class DeviceHardware:
    """Assembled hardware bundle produced by build_hardware.

    ``network_controls`` and ``transmit_pump`` are the same
    ``HardwareNetworkControls`` instance seen through its two declared faces
    — the builder constructs it once and assigns both slots from it. Rules
    reach the send-only ``network_controls``; the runtime loop reaches the
    lifecycle-pumping ``transmit_pump``. Neither call site downcasts to the
    other's type.
    """

    __slots__ = (
        "accelerometer",
        "buttons",
        "ir_receiver",
        "network_controls",
        "outputs",
        "transmit_pump",
    )

    def __init__(
        self,
        outputs: list[EffectOutput],
        buttons: DebouncedButtons,
        accelerometer: object | None,
        network_controls: NetworkControls,
        transmit_pump: TransmitPump,
        ir_receiver: InfraredReceiver | None,
    ) -> None:
        self.outputs: list[EffectOutput] = outputs
        self.buttons: DebouncedButtons = buttons
        self.accelerometer: object | None = accelerometer
        self.network_controls: NetworkControls = network_controls
        self.transmit_pump: TransmitPump = transmit_pump
        self.ir_receiver: InfraredReceiver | None = ir_receiver
