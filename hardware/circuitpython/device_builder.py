"""Device-only builder — resolves pin strings and assembles DeviceHardware.

Deploy-watch only: imports board, busio, digitalio, microcontroller.

Every per-component driver library (``adafruit_is31fl3741``, ``neopixel``,
``pulseio``, the audio stack, ``adafruit_lis3dh``, ``adafruit_drv2605``,
``adafruit_rfm69``) is imported inside the setup helper or branch that builds
that component, not here at module scope — so importing this module, or
building a config that doesn't need a component, never requires that
component's library to be installed. ``adafruit_rfm69`` itself is only ever
imported by ``hardware.circuitpython.rfm69_radio_transport``, reached here
through a deferred import in ``_setup_radio``.
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
from engine.network import IR_EMITTERS
from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import (
    AudioConfig,
    DeviceConfig,
    I2CConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    RadioConfig,
    SPIConfig,
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
from hardware.shared.radio_transport import RadioTransport

__all__ = [
    "build_hardware",
    "load_device_config",
    "open_config_i2c",
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

    *i2c_config* with ``enabled=False`` builds no bus at all — distinct from
    an absent *i2c_config*, which still falls back to the board's default
    pins. This is the only place that distinction is made; every other
    caller sees ``i2c=None`` either way.
    """
    if i2c_config is not None and not i2c_config.enabled:
        return None
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


def open_config_i2c(device_config: DeviceConfig, board_module: object = board) -> busio.I2C | None:
    """Return an I2C bus on *device_config*'s declared (or board-default) SDA/SCL pins.

    A public entry point onto :func:`_setup_i2c` for callers that need a bus
    without a full :func:`build_hardware` call -- e.g. a profiler that wraps
    the returned bus in ``CountingI2C`` before injecting it back into
    ``build_hardware``'s ``i2c=`` seam, so the injected bus lands on exactly
    the pins ``build_hardware`` would have chosen itself. Honours
    *device_config*'s ``i2c`` section: ``enabled=False`` builds no bus at
    all, named pins are resolved via ``_resolve_pin`` (raising a field-named
    ``ValueError`` for an unknown pin), and a ``RuntimeError`` from
    ``busio.I2C`` (no pull-up found) is caught and returns ``None`` rather
    than propagating.

    Unlike ``board.STEMMA_I2C()``, the returned bus is a plain ``busio.I2C``
    that CircuitPython tears down on reload rather than holding
    ``never_reset`` -- so a profiler run never leaves the I2C peripheral
    claimed for the next program (e.g. a demo) that constructs its own bus
    on the same pins.
    """
    return _setup_i2c(device_config.i2c, board_module)


def _setup_spi(spi_config: SPIConfig | None, board_module: object) -> busio.SPI | None:
    """Return the shared SPI bus the radio (and any future SPI peripheral)
    is built on, or ``None`` when *spi_config* is disabled.

    Mirrors ``_setup_i2c``'s shape: with *spi_config* present, ``sck``/
    ``mosi``/``miso`` are resolved by name against *board_module*; absent
    falls back to ``board_module.SPI()``. ``enabled=False`` builds no bus at
    all — distinct from an absent *spi_config*, which still falls back to
    the board's default SPI bus. Unlike ``busio.I2C``, ``busio.SPI`` does not
    probe for an attached device at construction time, so there is no
    analogous "no pull-up" fallback to catch here.
    """
    if spi_config is not None and not spi_config.enabled:
        return None
    if spi_config is not None:
        sck = _resolve_pin(board_module, "spi.sck", spi_config.sck)
        mosi = _resolve_pin(board_module, "spi.mosi", spi_config.mosi)
        miso = _resolve_pin(board_module, "spi.miso", spi_config.miso)
        return busio.SPI(sck, MOSI=mosi, MISO=miso)
    return board_module.SPI()


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
    for each in the order they were declared. An entry with ``enabled=False``
    is skipped outright — neither built nor probed, so a disabled matrix
    entry doesn't even trigger the missing-I2C-bus check below.

    Raises:
        RuntimeError: If an enabled matrix entry is declared but *i2c* is
            None (matrix pixels are config-gated, so a missing bus is a real
            wiring fault).
    """
    outputs: list[EffectOutput] = []
    for pixels_cfg in pixels_configs:
        if not pixels_cfg.enabled:
            continue
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


def _setup_accelerometer(i2c: busio.I2C) -> object:
    """Return a configured LIS3DH accelerometer on *i2c*.

    ``adafruit_lis3dh`` is imported here, not at module load, so a config
    with no ``accelerometer`` section never requires the library to be
    installed.

    Accelerometer is config-gated, not presence-probed: the caller only
    reaches this once ``config.accelerometer`` is declared and enabled, so a
    declared accelerometer that can't be built here is a wiring fault, not a
    normal "not present" case.

    Raises:
        ImportError: If ``adafruit_lis3dh`` is not installed.
        Exception: Whatever ``adafruit_lis3dh.LIS3DH_I2C`` raises if the
            sensor cannot be reached on *i2c*.
    """
    import adafruit_lis3dh

    return adafruit_lis3dh.LIS3DH_I2C(i2c)


def _setup_drv2605(i2c: busio.I2C) -> object:
    """Return a configured DRV2605 haptic driver on *i2c*.

    ``adafruit_drv2605`` is imported here, not at module load, so a config
    with no ``haptics`` section never requires the library to be installed.

    Haptics is config-gated, not presence-probed: the caller only reaches
    this once ``config.haptics`` is declared and enabled, so a declared
    driver that can't be built here is a wiring fault, not a normal "not
    present" case.

    Raises:
        ImportError: If ``adafruit_drv2605`` is not installed.
        Exception: Whatever ``adafruit_drv2605.DRV2605`` raises if the
            driver cannot be reached on *i2c*.
    """
    import adafruit_drv2605

    return adafruit_drv2605.DRV2605(i2c)


def _require_i2c(i2c: busio.I2C | None, section: str) -> busio.I2C:
    """Return *i2c*, raising if a declared *section* has no bus to build its chip on."""
    if i2c is None:
        raise RuntimeError(f"{section} section is declared but no I2C bus is available")
    return i2c


def _require_spi(spi: busio.SPI | None, section: str) -> busio.SPI:
    """Return *spi*, raising if a declared *section* has no bus to build its chip on."""
    if spi is None:
        raise RuntimeError(f"{section} section is declared but no SPI bus is available")
    return spi


def _setup_radio(spi: busio.SPI, radio_cfg: RadioConfig, board_module: object) -> RadioTransport:
    """Return a configured Rfm69RadioTransport from *radio_cfg* on *spi*.

    ``Rfm69RadioTransport`` (``hardware.circuitpython.rfm69_radio_transport``)
    is imported here, not at module load, so a config with no ``radio``
    section never requires ``adafruit_rfm69`` to be installed — that module
    is the only place ``adafruit_rfm69`` itself is imported.
    """
    from hardware.circuitpython.rfm69_radio_transport import Rfm69RadioTransport

    cs = digitalio.DigitalInOut(_resolve_pin(board_module, "radio.cs", radio_cfg.cs))
    reset = digitalio.DigitalInOut(_resolve_pin(board_module, "radio.reset", radio_cfg.reset))
    return Rfm69RadioTransport(spi, cs, reset, radio_cfg.frequency, radio_cfg.node)


def _setup_audio(audio_cfg: AudioConfig, board_module: object) -> AudioEffectOutput:
    """Return a configured AudioEffectOutput from *audio_cfg*.

    Audio is config-gated rather than presence-probed, so unlike the
    Optional-returning accelerometer/drv2605 helpers there is no absent case
    — the caller's ``config.audio is not None and config.audio.enabled``
    guard is the only gate.

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
    emitter_pins: dict[str, microcontroller.Pin],
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

    *emitter_pins* maps an emitter constant (a key of ``engine.network.
    IR_EMITTERS``) to the pin it is wired to; an emitter absent from the
    mapping is skipped. Transmitters are wired in ``IR_EMITTERS`` order,
    independent of *emitter_pins*' own key order.

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
    for emitter in IR_EMITTERS:
        pin = emitter_pins.get(emitter)
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
    accelerometer, haptics driver) instead of the bus this function would
    otherwise construct itself.

    Every component this builder attaches — pixels, audio, IR, the
    accelerometer, haptics, and the RFM69 radio — is config-gated: it is
    built only when its section is declared *and* enabled in *config*, and
    none is ever probed by physical presence. A section with
    ``enabled=False`` is retained by the parser but treated the same as
    absent here — neither built nor probed, and its driver library is never
    imported. A declared-and-enabled accelerometer or haptics section whose
    chip can't be constructed (including no I2C bus being available — e.g. a
    disabled ``i2c`` section) raises, mirroring how a declared matrix with no
    I2C bus raises. A declared-and-enabled radio section whose SPI bus can't
    be reached (disabled or unbuildable) raises the same way, against the
    shared SPI bus this builder constructs once (configured ``sck``/``mosi``/
    ``miso`` pins, or ``board.SPI()`` when the ``spi`` section is absent; no
    bus when ``spi`` is disabled — see ``_setup_spi``).

    Raises:
        ValueError: If a declared pin name does not exist on the board.
        RuntimeError: If pixels.type is 'matrix' but no I2C bus is available,
            an accelerometer/haptics section is declared but no I2C bus is
            available, or a radio section is declared but no SPI bus is
            available.
    """
    _setup_external_power()
    if i2c is None:
        i2c = _setup_i2c(config.i2c, board_module)
    spi = _setup_spi(config.spi, board_module)

    outputs: list[EffectOutput] = []
    outputs.extend(_setup_pixels(config.pixels, board_module, i2c))

    button_pins = [
        _resolve_pin(board_module, f"buttons[{i}]", name) for i, name in enumerate(config.buttons)
    ]
    buttons = _setup_buttons(*button_pins)

    accelerometer = None
    if config.accelerometer is not None and config.accelerometer.enabled:
        accelerometer = _setup_accelerometer(_require_i2c(i2c, "accelerometer"))

    if config.audio is not None and config.audio.enabled:
        outputs.append(_setup_audio(config.audio, board_module))

    if config.haptics is not None and config.haptics.enabled:
        driver = _setup_drv2605(_require_i2c(i2c, "haptics"))
        # Drv2605EffectOutput's own module imports adafruit_drv2605 at load
        # time, so this import is deferred here — reached only once
        # _setup_drv2605 has already confirmed the library is importable.
        from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

        outputs.append(Drv2605EffectOutput(driver))

    radio = None
    if config.radio is not None and config.radio.enabled:
        radio = _setup_radio(_require_spi(spi, "radio"), config.radio, board_module)

    transmitters: dict[str, InfraredTransmitter] = {}
    ir_receiver = None
    if config.ir is not None and config.ir.enabled:
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

        transmitters, ir_receiver = _setup_ir(
            rx_pins,
            emitter_pins,
            encoder=encoder,
            decoder=decoder,
        )

    # One HardwareNetworkControls instance, seen through two declared faces:
    # rules reach it as the send-only NetworkControls; the runtime loop
    # reaches the same object as TransmitPump to pump transmit lifecycle.
    hardware_network_controls = HardwareNetworkControls(transmitters, radio=radio)

    return DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        network_controls=hardware_network_controls,
        transmit_pump=hardware_network_controls,
        ir_receiver=ir_receiver,
        radio=radio,
    )
