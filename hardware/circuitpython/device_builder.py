"""Device-only builder — resolves pin strings and assembles DeviceHardware.

Deploy-watch only: imports board, busio, pulseio, digitalio.
"""

from __future__ import annotations

import json

import board

import hardware.circuitpython.propmaker as propmaker
from engine.audio import AudioRegistry
from engine.network import HardwareNetworkControls
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.shared.device_config import (
    DEFAULT_DEVICE_CONFIG,
    DeviceConfig,
    MatrixPixelsConfig,
    parse_device_config,
)
from hardware.shared.ir_protocol import AuraInfraredDecoder, AuraInfraredEncoder

__all__ = [
    "DeviceHardware",
    "build_hardware",
    "load_device_config",
]


class DeviceHardware:
    """Assembled hardware bundle produced by build_hardware."""

    __slots__ = ("accelerometer", "buttons", "ir_receiver", "network_controls", "outputs")

    def __init__(
        self,
        outputs: list[object],
        buttons: object,
        accelerometer: object | None,
        network_controls: HardwareNetworkControls,
        ir_receiver: object | None,
    ) -> None:
        self.outputs: list[object] = outputs
        self.buttons: object = buttons
        self.accelerometer: object | None = accelerometer
        self.network_controls: HardwareNetworkControls = network_controls
        self.ir_receiver: object | None = ir_receiver


def _resolve_pin(board_module: object, field: str, name: str) -> object:
    try:
        return getattr(board_module, name)
    except AttributeError:
        raise ValueError(f"{field}: pin '{name}' not found on board") from None


def load_device_config() -> DeviceConfig:
    """Load config from aura-device.json, falling back to DEFAULT_DEVICE_CONFIG."""
    try:
        with open("aura-device.json") as f:
            mapping = json.load(f)
        return parse_device_config(mapping)
    except OSError:
        print("aura-device.json not found — using default device config")
        return parse_device_config(DEFAULT_DEVICE_CONFIG)


def build_hardware(
    config: DeviceConfig,
    board_module: object = board,
    ir_encoder: object | None = None,
    ir_decoder: object | None = None,
) -> DeviceHardware:
    """Assemble DeviceHardware from a parsed DeviceConfig.

    Raises:
        ValueError: If a declared pin name does not exist on the board.
    """
    propmaker.setup_external_power()
    i2c = propmaker.setup_i2c()

    outputs: list[object] = []

    if isinstance(config.pixels, MatrixPixelsConfig):
        matrix = propmaker.setup_matrix_is31fl3741(i2c)
        outputs.append(
            IS31FL3741EffectOutput(
                matrix,
                cols=config.pixels.cols,
                scope_rows=config.pixels.scope_rows,
            )
        )

    button_pins = [
        _resolve_pin(board_module, f"buttons[{i}]", name) for i, name in enumerate(config.buttons)
    ]
    buttons = propmaker.setup_buttons(*button_pins)

    accelerometer = None
    try:
        accelerometer = propmaker.setup_accelerometer(i2c)
    except Exception:
        print("accelerometer not reachable — omitting from hardware bundle")

    motor = None
    try:
        motor = propmaker.setup_drv2605(i2c)
    except Exception:
        print("drv2605 not reachable — omitting from hardware bundle")

    if config.audio is not None:
        audio_registry = AudioRegistry()
        for clip_name, clip_path in config.audio.clips.items():
            audio_registry.register(clip_name, clip_path)

        audio_output = AudioEffectOutput(
            audio_registry,
            max_volume=config.audio.max_volume,
            num_voices=config.audio.voices,
            i2s_bit_clock=board_module.I2S_BIT_CLOCK,
            i2s_word_select=board_module.I2S_WORD_SELECT,
            i2s_data=board_module.I2S_DATA,
        )
        outputs.append(audio_output)

    if motor is not None:
        outputs.append(Drv2605EffectOutput(motor))

    transmitters: dict[str, object] = {}
    ir_receiver = None
    if config.ir is not None:
        encoder = ir_encoder if ir_encoder is not None else AuraInfraredEncoder()
        decoder = ir_decoder if ir_decoder is not None else AuraInfraredDecoder()

        rx_pin = _resolve_pin(board_module, "ir.rx", config.ir.rx)
        emitter_pins: dict[str, object] = {}
        for emitter_key, pin_name in config.ir.emitters.items():
            emitter_pins[emitter_key] = _resolve_pin(board_module, f"ir.{emitter_key}", pin_name)

        line_pin = emitter_pins.get("line")
        cone_pin = emitter_pins.get("cone")
        aoe_pin = emitter_pins.get("area_of_effect")

        transmitters, ir_receiver = propmaker.setup_ir(
            rx_pin,
            line_pin,
            cone_pin=cone_pin,
            aoe_pin=aoe_pin,
            encoder=encoder,
            decoder=decoder,
        )

    network_controls = HardwareNetworkControls(transmitters)

    return DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        network_controls=network_controls,
        ir_receiver=ir_receiver,
    )
