"""Device-only builder — resolves pin strings and assembles DeviceHardware.

Deploy-watch only: imports board, busio, pulseio, digitalio.
"""

from __future__ import annotations

import json
import time

import adafruit_is31fl3741
import board
import busio
import digitalio
import microcontroller
import neopixel
import pulseio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from engine.audio import AudioRegistry
from engine.effects.manager import EffectOutput
from engine.network import AREA_OF_EFFECT, CONE, LINE, HardwareNetworkControls
from engine.state import NetworkControls
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import (
    DEFAULT_DEVICE_CONFIG,
    DeviceConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    parse_device_config,
)
from hardware.shared.ir_protocol import (
    AuraInfraredDecoder,
    AuraInfraredEncoder,
    InfraredDecoder,
    InfraredEncoder,
)
from hardware.shared.ir_transport import InfraredSingleReceiver, InfraredTransmitter, IrTransmitGate

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
        outputs: list[EffectOutput],
        buttons: DebouncedButtons,
        accelerometer: object | None,
        network_controls: NetworkControls,
        ir_receiver: InfraredSingleReceiver | None,
    ) -> None:
        self.outputs: list[EffectOutput] = outputs
        self.buttons: DebouncedButtons = buttons
        self.accelerometer: object | None = accelerometer
        self.network_controls: NetworkControls = network_controls
        self.ir_receiver: InfraredSingleReceiver | None = ir_receiver


def _resolve_pin(board_module: object, field: str, name: str) -> microcontroller.Pin:
    try:
        return getattr(board_module, name)
    except AttributeError:
        raise ValueError(f"{field}: pin '{name}' not found on board") from None


def _setup_external_power() -> None:
    """Enable the PropMaker's EXTERNAL_POWER rail (powers NeoPixels, audio amp, and other
    peripherals)."""
    power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
    power.switch_to_output(value=True)


def _setup_i2c() -> busio.I2C:
    """Return an I2C bus on the board's default SDA/SCL pins."""
    return busio.I2C(board.SCL, board.SDA)


def _setup_matrix_is31fl3741(i2c: busio.I2C) -> Adafruit_RGBMatrixQT:
    """Return a configured IS31FL3741 driver on *i2c*.

    Retries until the matrix responds (useful if the I2C bus is still
    settling at boot).  Sets LED scaling to 0x33 and global current to 0xFF
    then enables the matrix.
    """
    while True:
        try:
            matrix = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
            break
        except Exception:
            time.sleep(1)
    matrix.set_led_scaling(0x33)
    matrix.global_current = 0xFF
    matrix.enable = True
    return matrix


def _setup_buttons(*pins: microcontroller.Pin) -> DebouncedButtons:
    """Return a ``DebouncedButtons`` instance for the given pins with pull-up resistors."""
    labels = [chr(ord("A") + i) for i in range(len(pins))]
    pairs = []
    for label, pin in zip(labels, pins):
        btn = digitalio.DigitalInOut(pin)
        btn.switch_to_input(pull=digitalio.Pull.UP)
        pairs.append((label, lambda p=btn: p.value))
    return DebouncedButtons(pairs)


def _setup_accelerometer(i2c: busio.I2C) -> object | None:
    """Return a configured LIS3DH accelerometer on *i2c*, or ``None`` if absent.

    Prints a distinct warning depending on the failure mode:
    - ``"accelerometer library not installed"`` when ``adafruit_lis3dh`` cannot
      be imported.
    - ``"accelerometer not found on I2C bus"`` when the library is present but
      the sensor cannot be reached.
    """
    try:
        import adafruit_lis3dh
    except ImportError:
        print("accelerometer library not installed")
        return None
    try:
        return adafruit_lis3dh.LIS3DH_I2C(i2c)
    except Exception:
        print("accelerometer not found on I2C bus")
        return None


def _setup_drv2605(i2c: busio.I2C) -> object | None:
    """Return a configured DRV2605 haptic motor driver on *i2c*, or ``None`` if absent.

    Prints a distinct warning depending on the failure mode:
    - ``"drv2605 library not installed"`` when ``adafruit_drv2605`` cannot
      be imported.
    - ``"drv2605 not found on I2C bus"`` when the library is present but
      the driver cannot be reached.
    """
    try:
        import adafruit_drv2605
    except ImportError:
        print("drv2605 library not installed")
        return None
    try:
        return adafruit_drv2605.DRV2605(i2c)
    except Exception:
        print("drv2605 not found on I2C bus")
        return None


def _setup_ir(
    rx_pin: microcontroller.Pin,
    line_pin: microcontroller.Pin | None,
    cone_pin: microcontroller.Pin | None = None,
    aoe_pin: microcontroller.Pin | None = None,
    encoder: InfraredEncoder | None = None,
    decoder: InfraredDecoder | None = None,
) -> tuple[dict[str, InfraredTransmitter], InfraredSingleReceiver]:
    """Wire IR transceiver pins and return (transmitters, receiver).

    encoder and decoder must use the same wire protocol — a mismatched pair
    silently fails to decode received frames with no error raised.

    Constructs one :class:`IrTransmitGate` and injects the same instance into
    the receiver and every transmitter — the single assembly point for
    self-echo suppression. The gate itself is not returned; it lives only as
    a shared reference between the receiver and transmitters it wires here.
    """
    if line_pin is None:
        raise ValueError("line_pin is required — the LINE emitter must always be wired")

    if encoder is None:
        encoder = AuraInfraredEncoder()
    if decoder is None:
        decoder = AuraInfraredDecoder()

    gate = IrTransmitGate()

    pulsein = pulseio.PulseIn(rx_pin, maxlen=256, idle_state=True)
    reader = PulseInReader(pulsein)
    receiver = InfraredSingleReceiver(reader, decoder, gate=gate)

    transmitters: dict[str, InfraredTransmitter] = {}
    for emitter, pin in ((LINE, line_pin), (CONE, cone_pin), (AREA_OF_EFFECT, aoe_pin)):
        if pin is None:
            continue
        pulseout = pulseio.PulseOut(pin, frequency=38000, duty_cycle=0x8000)
        writer = PulseOutWriter(pulseout)
        transmitters[emitter] = InfraredTransmitter(writer, encoder, gate=gate)

    return transmitters, receiver


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
    ir_encoder: InfraredEncoder | None = None,
    ir_decoder: InfraredDecoder | None = None,
    i2c: busio.I2C | None = None,
) -> DeviceHardware:
    """Assemble DeviceHardware from a parsed DeviceConfig.

    *i2c*, if supplied, is used for every I2C peripheral (matrix,
    accelerometer, motor) instead of the bus this function would otherwise
    construct itself — the seam bandwidth profilers use to wrap the bus in
    ``CountingI2C`` while still driving production ``EffectOutput``s.

    Raises:
        ValueError: If a declared pin name does not exist on the board.
    """
    _setup_external_power()
    if i2c is None:
        i2c = _setup_i2c()

    outputs: list[EffectOutput] = []

    for pixels_cfg in config.pixels:
        if isinstance(pixels_cfg, MatrixPixelsConfig):
            matrix = _setup_matrix_is31fl3741(i2c)
            outputs.append(
                IS31FL3741EffectOutput(
                    matrix,
                    cols=pixels_cfg.cols,
                    scope_rows=pixels_cfg.scope_rows,
                )
            )
        elif isinstance(pixels_cfg, NeoPixelPixelsConfig):
            for strip_cfg in pixels_cfg.strips:
                pin = _resolve_pin(board_module, "pixels.pin", strip_cfg.pin)
                hw_strip = neopixel.NeoPixel(
                    pin,
                    strip_cfg.count,
                    pixel_order=strip_cfg.order,
                    auto_write=False,
                )
                outputs.append(
                    NeoPixelEffectOutput(hw_strip, strip_cfg.scope_pixels, strip_cfg.brightness)
                )
            for scope_key, scope_cfg in pixels_cfg.scopes.items():
                pin = _resolve_pin(board_module, f"pixels.scopes.{scope_key}.pin", scope_cfg.pin)
                hw_strip = neopixel.NeoPixel(
                    pin,
                    scope_cfg.count,
                    pixel_order=scope_cfg.order,
                    auto_write=False,
                )
                outputs.append(
                    NeoPixelEffectOutput(
                        hw_strip,
                        {scope_key: range(0, scope_cfg.count)},
                        scope_cfg.brightness,
                    )
                )

    button_pins = [
        _resolve_pin(board_module, f"buttons[{i}]", name) for i, name in enumerate(config.buttons)
    ]
    buttons = _setup_buttons(*button_pins)

    accelerometer = None
    try:
        accelerometer = _setup_accelerometer(i2c)
    except Exception:
        print("accelerometer not reachable — omitting from hardware bundle")

    motor = None
    try:
        motor = _setup_drv2605(i2c)
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

    transmitters: dict[str, InfraredTransmitter] = {}
    ir_receiver = None
    if config.ir is not None:
        encoder = ir_encoder if ir_encoder is not None else AuraInfraredEncoder()
        decoder = ir_decoder if ir_decoder is not None else AuraInfraredDecoder()

        rx_pin = _resolve_pin(board_module, "ir.rx", config.ir.rx)
        emitter_pins: dict[str, microcontroller.Pin] = {}
        for emitter_key, pin_name in config.ir.emitters.items():
            emitter_pins[emitter_key] = _resolve_pin(board_module, f"ir.{emitter_key}", pin_name)

        line_pin = emitter_pins.get("line")
        cone_pin = emitter_pins.get("cone")
        aoe_pin = emitter_pins.get("area_of_effect")

        transmitters, ir_receiver = _setup_ir(
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
