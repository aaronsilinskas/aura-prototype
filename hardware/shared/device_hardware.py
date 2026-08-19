"""DeviceHardware — the board-free bundle build_hardware returns. No board imports."""

from __future__ import annotations

from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.state import NetworkControls
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.radio_transport import RadioTransport

__all__ = ["DeviceHardware"]


class DeviceHardware:
    """Assembled hardware bundle produced by build_hardware.

    ``ir`` is the single owner of the whole IR subsystem (transmitters,
    receiver, shared transmit gate) — the same ``InfraredTransceiver``
    instance ``HardwareNetworkControls.send_ir`` reaches through. ``None``
    exactly when there is no ``ir`` section declared (or it is disabled),
    the same condition under which the old ``ir_receiver`` slot was
    ``None``.

    ``radio`` is the same seam ``HardwareNetworkControls.send_radio`` reaches
    through — ``None`` on a device with no radio peripheral declared.

    ``storage`` is typed as the port (``DeviceStorage``), never the concrete
    ``SdCardStorage`` adapter — ``None`` on a device with no ``sdcard``
    section declared and enabled.

    ``audio_registry`` is the same ``AudioRegistry`` instance the built
    ``AudioEffectOutput`` resolves clips through — ``None`` on a device with
    no ``audio`` section declared and enabled. ``app.build_scene_runtime``
    scans effect-pack sounds into it and installs it as ``SceneManager``'s
    audio-overlay admin.

    ``magnetometer`` is typed like ``accelerometer`` (``object | None``, no
    concrete driver import here) — ``None`` on a device with no
    ``magnetometer`` section declared and enabled.
    """

    __slots__ = (
        "accelerometer",
        "audio_registry",
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
        accelerometer: object | None,
        magnetometer: object | None,
        network_controls: NetworkControls,
        ir: InfraredTransceiver | None,
        radio: RadioTransport | None,
        storage: DeviceStorage | None,
        audio_registry: AudioRegistry | None,
    ) -> None:
        self.outputs: list[EffectOutput] = outputs
        self.buttons: DebouncedButtons = buttons
        self.accelerometer: object | None = accelerometer
        self.magnetometer: object | None = magnetometer
        self.network_controls: NetworkControls = network_controls
        self.ir: InfraredTransceiver | None = ir
        self.radio: RadioTransport | None = radio
        self.storage: DeviceStorage | None = storage
        self.audio_registry: AudioRegistry | None = audio_registry
