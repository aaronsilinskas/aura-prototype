"""Device-only builder — resolves pin strings and assembles DeviceHardware.

Deploy-watch only: imports board, busio, digitalio, microcontroller.

Every per-component driver library (``adafruit_is31fl3741``, ``neopixel``,
``pulseio``, the audio stack, ``adafruit_drv2605``) is imported inside the
setup helper or branch that builds that component, not here at module scope —
so importing this module, or building a config that doesn't need a component,
never requires that component's library to be installed.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TYPE_CHECKING, Final
except ImportError:
    TYPE_CHECKING = False

# Type-checker-only imports for driver types used solely as annotations —
# real imports of these libraries stay deferred to the branch that builds
# the corresponding component (see module docstring), so this block never
# runs, and never requires the libraries, outside a type checker.
if TYPE_CHECKING:
    from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

    from hardware.circuitpython.audio_output import AudioEffectOutput

import time

import board
import busio
import digitalio
import microcontroller

from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import (
    AudioConfig,
    DeviceConfig,
    I2CConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
)
from hardware.shared.device_config import load_device_config as _load_shared_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_protocol import (
    AuraInfraredDecoder,
    AuraInfraredEncoder,
    InfraredDecoder,
    InfraredEncoder,
)
from hardware.shared.ir_transport import (
    InfraredMultiReceiver,
    InfraredReceiver,
    InfraredSingleReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseWriter,
)
from hardware.shared.network_controls import HardwareNetworkControls

__all__ = [
    "build_hardware",
    "load_device_config",
]


def _resolve_pin(board_module: object, field: str, name: str) -> microcontroller.Pin:
    try:
        return getattr(board_module, name)
    except AttributeError:
        raise ValueError(f"{field}: pin '{name}' not found on board") from None


def _setup_external_power() -> None:
    """Enable the PropMaker's EXTERNAL_POWER rail (powers NeoPixels, audio amp, and other
    peripherals), if the board has one."""
    if not hasattr(board, "EXTERNAL_POWER"):
        return
    power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
    power.switch_to_output(value=True)


def _setup_i2c(i2c_config: I2CConfig | None, board_module: object) -> busio.I2C | None:
    """Return an I2C bus on the configured (or board-default) SDA/SCL pins,
    or ``None`` if no I2C devices are wired (``busio.I2C`` requires a
    pull-up from an attached device to construct successfully).

    When *i2c_config* is present, ``sda``/``scl`` are resolved by name
    against *board_module* — for boards (e.g. the Pimoroni Pico 2W) whose
    ``board`` module lacks the ``SCL``/``SDA`` aliases. When absent, falls
    back to ``board_module.SCL``/``board_module.SDA`` as before. A board
    missing those aliases that also omits the config section raises
    ``AttributeError`` uncaught — the intended nudge to add an ``i2c``
    section to aura-device.json.
    """
    if i2c_config is not None:
        scl = _resolve_pin(board_module, "i2c.scl", i2c_config.scl)
        sda = _resolve_pin(board_module, "i2c.sda", i2c_config.sda)
    else:
        scl = board_module.SCL
        sda = board_module.SDA
    try:
        return busio.I2C(scl, sda)
    except RuntimeError:
        return None


_MATRIX_STARTUP_TIMEOUT_S: Final = 3


def _setup_matrix_is31fl3741(i2c: busio.I2C, brightness: float) -> Adafruit_RGBMatrixQT:
    """Return a configured IS31FL3741 driver on *i2c*.

    Retries construction for up to :data:`_MATRIX_STARTUP_TIMEOUT_S` seconds
    (useful if the I2C bus is still settling at boot), sleeping ~1s between
    attempts. Drives LED scaling from *brightness* (``round(brightness *
    0xFF)``), leaves global current pinned at 0xFF, then enables the matrix.

    ``adafruit_is31fl3741`` and ``Adafruit_RGBMatrixQT`` are imported here,
    not at module load, so a config with no matrix entry never requires the
    library to be installed.

    Raises:
        RuntimeError: If the matrix has not responded within the timeout.
    """
    import adafruit_is31fl3741
    from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

    deadline = time.monotonic() + _MATRIX_STARTUP_TIMEOUT_S
    matrix = None
    while matrix is None:
        try:
            matrix = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"IS31FL3741 matrix did not respond within {_MATRIX_STARTUP_TIMEOUT_S}s"
                ) from None
            time.sleep(1)
    scaling = round(brightness * 0xFF)
    matrix.set_led_scaling(scaling)
    matrix.global_current = 0xFF
    matrix.enable = True
    return matrix


def _setup_neopixels(pixels_cfg: NeoPixelPixelsConfig, board_module: object) -> list[EffectOutput]:
    """Return one NeoPixelEffectOutput per physical strip declared in *pixels_cfg*.

    Covers both the modern ``strips`` list (each strip carrying its own
    ``scope_pixels`` segments) and the legacy per-scope ``scopes`` map, where
    each entry becomes a single strip spanning the whole scope.

    ``neopixel`` is imported here, not at module load, so a config with no
    NeoPixel entry never requires the library to be installed.
    """
    import neopixel

    outputs: list[EffectOutput] = []
    for strip_cfg in pixels_cfg.strips:
        pin = _resolve_pin(board_module, "pixels.pin", strip_cfg.pin)
        hw_strip = neopixel.NeoPixel(
            pin,
            strip_cfg.count,
            pixel_order=strip_cfg.order,
            brightness=strip_cfg.brightness,
            auto_write=False,
        )
        outputs.append(NeoPixelEffectOutput(hw_strip, strip_cfg.scope_pixels))
    for scope_key, scope_cfg in pixels_cfg.scopes.items():
        pin = _resolve_pin(board_module, f"pixels.scopes.{scope_key}.pin", scope_cfg.pin)
        hw_strip = neopixel.NeoPixel(
            pin,
            scope_cfg.count,
            pixel_order=scope_cfg.order,
            brightness=scope_cfg.brightness,
            auto_write=False,
        )
        outputs.append(NeoPixelEffectOutput(hw_strip, {scope_key: range(0, scope_cfg.count)}))
    return outputs


def _setup_pixels(
    pixels_configs: list[MatrixPixelsConfig | NeoPixelPixelsConfig],
    board_module: object,
    i2c: busio.I2C | None,
) -> list[EffectOutput]:
    """Return one EffectOutput per pixel output declared across *pixels_configs*.

    Dispatches each entry to the matrix or NeoPixel branch by type, in config
    order, so a device driving both a matrix and NeoPixel strips gets outputs
    for each in the order they were declared.

    Raises:
        RuntimeError: If a matrix entry is declared but *i2c* is None (matrix
            pixels are config-gated, not presence-probed like the
            accelerometer/motor, so a missing bus is a real wiring fault).
    """
    outputs: list[EffectOutput] = []
    for pixels_cfg in pixels_configs:
        if isinstance(pixels_cfg, MatrixPixelsConfig):
            if i2c is None:
                raise RuntimeError("pixels.type is 'matrix' but no I2C bus is available")
            # IS31FL3741EffectOutput's own module imports adafruit_is31fl3741 at load
            # time, so this import is deferred here alongside _setup_matrix_is31fl3741's.
            from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

            matrix = _setup_matrix_is31fl3741(i2c, pixels_cfg.brightness)
            outputs.append(
                IS31FL3741EffectOutput(
                    matrix,
                    cols=pixels_cfg.cols,
                    scope_rows=pixels_cfg.scope_rows,
                )
            )
        elif isinstance(pixels_cfg, NeoPixelPixelsConfig):
            outputs.extend(_setup_neopixels(pixels_cfg, board_module))
    return outputs


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


def _setup_audio(audio_cfg: AudioConfig, board_module: object) -> AudioEffectOutput:
    """Return a configured AudioEffectOutput from *audio_cfg*.

    Audio is config-gated rather than presence-probed, so unlike the
    Optional-returning accelerometer/drv2605 helpers there is no absent case
    — the caller's ``if config.audio is not None:`` guard is the only gate.

    ``AudioEffectOutput`` is imported here, not at module load — its module
    pulls in ``audiobusio``/``audiocore``/``audiomixer`` at import time, so a
    config with no audio section never requires the audio stack installed.
    """
    from hardware.circuitpython.audio_output import AudioEffectOutput

    audio_registry = AudioRegistry()
    for clip_name, clip_path in audio_cfg.clips.items():
        audio_registry.register(clip_name, clip_path)

    return AudioEffectOutput(
        audio_registry,
        max_volume=audio_cfg.max_volume,
        num_voices=audio_cfg.voices,
        i2s_bit_clock=_resolve_pin(board_module, "audio.i2s_bit_clock", audio_cfg.i2s_bit_clock),
        i2s_word_select=_resolve_pin(
            board_module, "audio.i2s_word_select", audio_cfg.i2s_word_select
        ),
        i2s_data=_resolve_pin(board_module, "audio.i2s_data", audio_cfg.i2s_data),
    )


def _make_writer(pin: microcontroller.Pin) -> PulseWriter:
    """Return the best non-blocking IR writer the silicon supports for *pin*.

    Selection is by import-probe: ``rp2pio`` is present only on RP2040/RP2350,
    so an importable ``rp2pio`` means the board can clock the carrier out via
    PIO/DMA — wire a :class:`PioPulseWriter` over its own state machine. On any
    other board ``rp2pio`` is missing and the blocking ``pulseio``-backed
    :class:`PulseOutWriter` is used. PIO availability is a property of the
    silicon, so there is no config knob; the PIO-writer module is imported here
    (not at module load) so it never executes on non-RP boards. The ``pulseio``
    fallback import is deferred the same way, so a board that never reaches
    this function (no IR section configured) never requires ``pulseio`` to be
    installed.

    Args:
        pin: The transmit pin the emitter is wired to.

    Returns:
        A :class:`PulseWriter` — a PIO-backed one on RP boards, else blocking.
    """
    try:
        import rp2pio  # noqa: F401  # present only on RP2040/RP2350
    except ImportError:
        import pulseio

        pulseout = pulseio.PulseOut(pin, frequency=38000, duty_cycle=0x8000)
        return PulseOutWriter(pulseout)

    from hardware.circuitpython.pio_pulse_writer import (
        PioPulseWriter,
        make_state_machine,
    )

    return PioPulseWriter(make_state_machine(pin))


def _setup_ir(
    rx_pins: list[microcontroller.Pin],
    line_pin: microcontroller.Pin | None,
    cone_pin: microcontroller.Pin | None = None,
    aoe_pin: microcontroller.Pin | None = None,
    encoder: InfraredEncoder | None = None,
    decoder: InfraredDecoder | None = None,
    writer_factory: Callable[[microcontroller.Pin], PulseWriter] = _make_writer,
) -> tuple[dict[str, InfraredTransmitter], InfraredReceiver]:
    """Wire IR transceiver pins and return (transmitters, receiver).

    encoder and decoder must use the same wire protocol — a mismatched pair
    silently fails to decode received frames with no error raised.

    One :class:`~hardware.circuitpython.infrared_io.PulseInReader` is built
    per entry in *rx_pins*. A single rx pin builds an
    :class:`~hardware.shared.ir_transport.InfraredSingleReceiver` wired with
    *decoder* directly — today's unchanged path. Two or more build an
    :class:`~hardware.shared.ir_transport.InfraredMultiReceiver`, passing
    ``type(decoder)`` as its ``decoder_factory`` so every reader gets its own
    fresh, symmetric decoder instance (the *decoder* instance itself is not
    reused across readers in that case).

    Constructs one :class:`IrTransmitGate` and injects the same instance into
    the receiver and every transmitter — the single assembly point for
    self-echo suppression. The gate itself is not returned; it lives only as
    a shared reference between the receiver and transmitters it wires here.

    *writer_factory* builds the :class:`PulseWriter` for each wired emitter
    pin — defaults to :func:`_make_writer`. This is assembly's only seam onto
    writer *selection*: swapping it in tests exercises transmitter wiring
    (one per emitter, sharing the gate, codec defaulting) without touching
    the silicon-coupled ``rp2pio`` probe in :func:`_make_writer`.

    ``pulseio`` is imported here, not at module load, so a config with no
    ``ir`` section never requires the library to be installed.
    """
    import pulseio

    if encoder is None:
        encoder = AuraInfraredEncoder()
    if decoder is None:
        decoder = AuraInfraredDecoder()

    gate = IrTransmitGate()

    readers = [
        PulseInReader(pulseio.PulseIn(rx_pin, maxlen=256, idle_state=True)) for rx_pin in rx_pins
    ]

    receiver: InfraredReceiver
    if len(readers) == 1:
        receiver = InfraredSingleReceiver(readers[0], decoder, gate=gate)
    else:
        receiver = InfraredMultiReceiver(readers, type(decoder), gate=gate)

    transmitters: dict[str, InfraredTransmitter] = {}
    for emitter, pin in ((LINE, line_pin), (CONE, cone_pin), (AREA_OF_EFFECT, aoe_pin)):
        if pin is None:
            continue
        writer = writer_factory(pin)
        transmitters[emitter] = InfraredTransmitter(writer, encoder, gate=gate)

    return transmitters, receiver


def load_device_config() -> DeviceConfig:
    """Load and parse aura-device.json from the device root."""
    return _load_shared_device_config()


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
    construct itself. If no bus is supplied and none can be constructed (no
    I2C devices wired to pull SDA/SCL high), the accelerometer and motor are
    silently omitted — matrix pixels, being config-gated rather than
    presence-probed, raise instead.

    Raises:
        ValueError: If a declared pin name does not exist on the board.
        RuntimeError: If pixels.type is 'matrix' but no I2C bus is available.
    """
    _setup_external_power()
    if i2c is None:
        i2c = _setup_i2c(config.i2c, board_module)

    outputs: list[EffectOutput] = []
    outputs.extend(_setup_pixels(config.pixels, board_module, i2c))

    button_pins = [
        _resolve_pin(board_module, f"buttons[{i}]", name) for i, name in enumerate(config.buttons)
    ]
    buttons = _setup_buttons(*button_pins)

    accelerometer = None
    if i2c is not None:
        try:
            accelerometer = _setup_accelerometer(i2c)
        except Exception:
            print("accelerometer not reachable — omitting from hardware bundle")

    motor = None
    if i2c is not None:
        try:
            motor = _setup_drv2605(i2c)
        except Exception:
            print("drv2605 not reachable — omitting from hardware bundle")

    if config.audio is not None:
        outputs.append(_setup_audio(config.audio, board_module))

    if motor is not None:
        # Drv2605EffectOutput's own module imports adafruit_drv2605 at load
        # time, so this import is deferred here — reached only once
        # _setup_drv2605's own presence probe has already confirmed the
        # library is importable.
        from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

        outputs.append(Drv2605EffectOutput(motor))

    transmitters: dict[str, InfraredTransmitter] = {}
    ir_receiver = None
    if config.ir is not None:
        encoder = ir_encoder if ir_encoder is not None else AuraInfraredEncoder()
        decoder = ir_decoder if ir_decoder is not None else AuraInfraredDecoder()

        rx_pin_names = config.ir.rx
        if len(rx_pin_names) == 1:
            rx_pins = [_resolve_pin(board_module, "ir.rx", rx_pin_names[0])]
        else:
            rx_pins = [
                _resolve_pin(board_module, f"ir.rx[{i}]", name)
                for i, name in enumerate(rx_pin_names)
            ]

        emitter_pins: dict[str, microcontroller.Pin] = {}
        for emitter_key, pin_name in config.ir.emitters.items():
            emitter_pins[emitter_key] = _resolve_pin(board_module, f"ir.{emitter_key}", pin_name)

        line_pin = emitter_pins.get("line")
        cone_pin = emitter_pins.get("cone")
        aoe_pin = emitter_pins.get("area_of_effect")

        transmitters, ir_receiver = _setup_ir(
            rx_pins,
            line_pin,
            cone_pin=cone_pin,
            aoe_pin=aoe_pin,
            encoder=encoder,
            decoder=decoder,
        )

    # One HardwareNetworkControls instance, seen through two declared faces:
    # rules reach it as the send-only NetworkControls; the runtime loop
    # reaches the same object as TransmitPump to pump transmit lifecycle.
    hardware_network_controls = HardwareNetworkControls(transmitters)

    return DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        network_controls=hardware_network_controls,
        transmit_pump=hardware_network_controls,
        ir_receiver=ir_receiver,
    )
