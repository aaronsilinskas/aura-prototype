"""Device-only builder — resolves pin strings and assembles DeviceHardware.

Deploy-watch only: imports board, busio, digitalio, microcontroller.

Every per-component driver library (``adafruit_is31fl3741``, ``neopixel``,
``pulseio``, the audio stack, ``adafruit_lis3dh``, ``adafruit_mmc56x3``,
``adafruit_drv2605``, ``adafruit_rfm69``, ``sdcardio``/``storage``) is imported inside the setup
helper or branch that builds that component, not here at module scope — so
importing this module, or building a config that doesn't need a component,
never requires that component's library to be installed. ``adafruit_rfm69``
itself is only ever imported by ``hardware.circuitpython.rfm69_radio_transport``,
reached here through a deferred import in ``_setup_radio``; ``sdcardio``/
``storage`` are only ever imported by ``hardware.circuitpython.sdcard_storage``,
reached here through a deferred import in ``_setup_sdcard``.
"""

from __future__ import annotations

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

# Type-checker-only imports for driver types used solely as annotations —
# real imports of these libraries stay deferred to the branch that builds
# the corresponding component (see module docstring), so this block never
# runs, and never requires the libraries, outside a type checker.
if TYPE_CHECKING:
    from hardware.circuitpython.audio_output import AudioEffectOutput

import time

import board
import busio
import digitalio
import microcontroller

from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.log import Logger

# Shared with CircuitPythonParts until build_hardware runs the Device assembly (#1055).
from hardware.circuitpython.circuitpython_parts import (
    SdCardMountError,
    _make_writer,
    _resolve_pin,
    _setup_accelerometer,
    _setup_drv2605,
    _setup_magnetometer,
    _setup_matrix_is31fl3741,
)
from hardware.circuitpython.infrared_io import PulseInReader
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.build_narration import (
    describe_accelerometer,
    describe_audio,
    describe_buttons,
    describe_haptics,
    describe_high_current_rail,
    describe_i2c,
    describe_ir,
    describe_magnetometer,
    describe_neopixel_current_budget,
    describe_pixel_entry,
    describe_radio,
    describe_sdcard,
    describe_spi,
    narrate_skip,
    narrate_step,
)
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import (
    AudioConfig,
    DeviceConfig,
    HighCurrentRailConfig,
    I2CConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    RadioConfig,
    SDCardConfig,
    SPIConfig,
)
from hardware.shared.device_config import load_device_config as _load_shared_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import PulseReader
from hardware.shared.ir_wiring import wire_ir
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.profiler_report import board_id
from hardware.shared.radio_transceiver import RadioTransceiver

__all__ = [
    "SdCardMountError",
    "build_hardware",
    "load_device_config",
    "open_config_i2c",
]


def _setup_high_current_rail(rail_cfg: HighCurrentRailConfig, board_module: object) -> None:
    """Resolve *rail_cfg*'s pin and drive it to the asserted or deasserted level.

    Unlike every other gated component, a disabled section (``enabled=False``)
    still drives its pin -- to the *deasserted* level, holding the high-current
    rail definitively off rather than leaving it floating (brown-out debugging).
    An enabled section drives the *asserted* level; ``active_high`` selects
    which physical level asserts.
    """
    pin = _resolve_pin(board_module, "high_current_rail.pin", rail_cfg.pin)
    output = digitalio.DigitalInOut(pin)
    asserted = rail_cfg.active_high
    level = asserted if rail_cfg.enabled else not asserted
    output.switch_to_output(value=level)


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
    pixels_cfg: MatrixPixelsConfig | NeoPixelPixelsConfig,
    board_module: object,
    i2c: busio.I2C | None,
) -> list[EffectOutput]:
    """Return the EffectOutputs for *pixels_cfg*, dispatching to the matrix or
    NeoPixel branch by type. An entry with ``enabled=False`` produces no
    outputs — neither built nor probed, so a disabled matrix entry doesn't
    even trigger the missing-I2C-bus check below. (The caller, ``build_hardware``,
    already filters out disabled entries before calling this, but the check
    stays here too since this is also called directly in tests.)

    Raises:
        RuntimeError: If an enabled matrix entry is declared but *i2c* is
            None (matrix pixels are config-gated, so a missing bus is a real
            wiring fault).
    """
    if not pixels_cfg.enabled:
        return []
    if isinstance(pixels_cfg, MatrixPixelsConfig):
        if i2c is None:
            raise RuntimeError("pixels.type is 'matrix' but no I2C bus is available")
        # IS31FL3741EffectOutput's own module imports adafruit_is31fl3741 at load
        # time, so this import is deferred here alongside _setup_matrix_is31fl3741's.
        from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput

        matrix = _setup_matrix_is31fl3741(i2c, pixels_cfg.brightness, pixels_cfg.address)
        return [
            IS31FL3741EffectOutput(
                matrix,
                cols=pixels_cfg.cols,
                scope_rows=pixels_cfg.scope_rows,
            )
        ]
    return _setup_neopixels(pixels_cfg, board_module)


def _setup_buttons(*pins: microcontroller.Pin) -> DebouncedButtons:
    """Return a ``DebouncedButtons`` instance for the given pins with pull-up resistors."""
    labels = [chr(ord("A") + i) for i in range(len(pins))]
    pairs = []
    for label, pin in zip(labels, pins):
        btn = digitalio.DigitalInOut(pin)
        btn.switch_to_input(pull=digitalio.Pull.UP)
        pairs.append((label, lambda p=btn: p.value))
    return DebouncedButtons(pairs)


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


def _setup_radio(spi: busio.SPI, radio_cfg: RadioConfig, board_module: object) -> RadioTransceiver:
    """Return a RadioTransceiver wrapping a configured Rfm69RadioTransport from
    *radio_cfg* on *spi*.

    A faithful mirror of :func:`_setup_ir`'s shape: assembles the live
    transport, then hands it to :class:`RadioTransceiver`, the single
    board-free owner of the radio subsystem's send and per-tick receive.

    ``Rfm69RadioTransport`` (``hardware.circuitpython.rfm69_radio_transport``)
    is imported here, not at module load, so a config with no ``radio``
    section never requires ``adafruit_rfm69`` to be installed — that module
    is the only place ``adafruit_rfm69`` itself is imported.
    """
    from hardware.circuitpython.rfm69_radio_transport import Rfm69RadioTransport

    cs = digitalio.DigitalInOut(_resolve_pin(board_module, "radio.cs", radio_cfg.cs))
    reset = digitalio.DigitalInOut(_resolve_pin(board_module, "radio.reset", radio_cfg.reset))
    transport = Rfm69RadioTransport(spi, cs, reset, radio_cfg.frequency, radio_cfg.node)
    return RadioTransceiver(transport)


def _setup_sdcard(spi: busio.SPI, sdcard_cfg: SDCardConfig, board_module: object) -> DeviceStorage:
    """Return a mounted SdCardStorage from *sdcard_cfg* on *spi*.

    ``SdCardStorage`` (``hardware.circuitpython.sdcard_storage``) is imported
    here, not at module load, so a config with no ``sdcard`` section never
    requires ``sdcardio``/``storage`` to be installed — that module is the
    only place either is imported. Unlike ``_setup_radio``'s ``cs``, which is
    wrapped in ``digitalio.DigitalInOut``, ``sdcardio.SDCard`` takes the raw
    resolved ``microcontroller.Pin`` directly.

    "Config-gated, never presence-probed" holds here too: this is only
    reached once ``config.sdcard`` is declared and enabled, so a mount
    failure is a wiring fault (no card fitted, or no FAT filesystem), not a
    normal "not present" case -- wrapped below into an :class:`SdCardMountError`
    rather than left as the vendor ``OSError``, unlike the radio's own chip-init
    error, which is left to propagate raw.

    Raises:
        SdCardMountError: Wrapping the ``OSError`` ``sdcardio``/``storage`` raise
            when the card is absent or unmountable, naming the section and
            the ``cs``/``mount`` context.
    """
    from hardware.circuitpython.sdcard_storage import SdCardStorage

    cs = _resolve_pin(board_module, "sdcard.cs", sdcard_cfg.cs)
    try:
        return SdCardStorage(spi, cs, sdcard_cfg.mount)
    except OSError as e:
        raise SdCardMountError(
            f"sdcard section is declared but the card at cs={sdcard_cfg.cs} "
            + f"mount={sdcard_cfg.mount} failed to mount: {e}"
        ) from e


def _setup_audio(
    audio_cfg: AudioConfig, board_module: object, audio_registry: AudioRegistry
) -> AudioEffectOutput:
    """Return a configured AudioEffectOutput from *audio_cfg*, resolving clips via
    *audio_registry*.

    Audio is config-gated rather than presence-probed, so unlike the
    Optional-returning accelerometer/drv2605 helpers there is no absent case
    — the caller's ``config.audio is not None and config.audio.enabled``
    guard is the only gate.

    *audio_registry* is built empty by the caller (``build_hardware``) and
    also exposed on ``DeviceHardware.audio_registry`` — populating its base
    (scanning effect-pack ``sounds/`` folders) and overlay (per-scene sounds)
    is ``app.build_scene_runtime``'s job, not this builder's.

    ``AudioEffectOutput`` is imported here, not at module load — its module
    pulls in ``audiobusio``/``audiocore``/``audiomixer`` at import time, so a
    config with no audio section never requires the audio stack installed.
    """
    from hardware.circuitpython.audio_output import AudioEffectOutput

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


def _setup_ir(
    rx_pins: list[microcontroller.Pin],
    emitter_pins: dict[str, microcontroller.Pin],
) -> tuple[InfraredTransceiver, str | None]:
    """Wire the IR hardware and return (transceiver, writer_kind).

    Builds one :class:`~hardware.circuitpython.infrared_io.PulseInReader`
    per entry in *rx_pins* and hands them, with :func:`_make_writer` as the
    per-emitter writer factory, to
    :func:`~hardware.shared.ir_wiring.wire_ir`, which owns the gate,
    receiver, transmitter and codec wiring.

    ``pulseio`` is imported here, not at module load, so a config with no
    ``ir`` section never requires the library to be installed.
    """
    import pulseio

    readers: list[PulseReader] = [
        PulseInReader(pulseio.PulseIn(rx_pin, maxlen=256, idle_state=True)) for rx_pin in rx_pins
    ]
    return wire_ir(readers, emitter_pins, lambda _emitter, pin: _make_writer(pin))


def load_device_config() -> DeviceConfig:
    """Load and parse aura-device.json from the device root."""
    return _load_shared_device_config()


def build_hardware(
    config: DeviceConfig,
    board_module: object = board,
    i2c: busio.I2C | None = None,
    logger: Logger | None = None,
) -> DeviceHardware:
    """Assemble DeviceHardware from a parsed DeviceConfig.

    *i2c*, if supplied, is used for every I2C peripheral (matrix,
    accelerometer, magnetometer, haptics driver) instead of the bus this
    function would otherwise construct itself.

    Every component this builder attaches — pixels, audio, IR, the
    accelerometer, magnetometer, haptics, and the RFM69 radio — is
    config-gated: it is built only when its section is declared *and*
    enabled in *config*, and none is ever probed by physical presence. A
    section with ``enabled=False`` is retained by the parser but treated the
    same as absent here — neither built nor probed, and its driver library
    is never imported. Single-call: every pin below is claimed once, without
    deiniting, so this must not be invoked twice in the same process.

    *logger*, if supplied, narrates each component below through a single
    :func:`~hardware.shared.build_narration.narrate_step` (built) or
    :func:`~hardware.shared.build_narration.narrate_skip` (disabled/absent)
    call -- see that module for the begin-before-build ordering guarantee
    every step relies on to attribute a failure to its own line. Omitted or
    ``None`` normalizes to :data:`~engine.log.Logger.SILENT` here, so every
    step below narrates unconditionally and an uninstrumented caller sees no
    output at all.

    Raises:
        ValueError: If a declared pin name does not exist on the board.
        RuntimeError: If pixels.type is 'matrix' but no I2C bus is available,
            an accelerometer/magnetometer/haptics section is declared but no
            I2C bus is available, a radio section is declared but no SPI bus
            is available, or an sdcard section is declared but no SPI bus is
            available or the card fails to mount.
    """
    if logger is None:
        logger = Logger.SILENT

    start = time.monotonic()
    logger.log(f"begin board={board_id()}")

    rail_cfg = config.high_current_rail
    if rail_cfg is not None:

        def _build_rail() -> tuple[None, str]:
            _setup_high_current_rail(rail_cfg, board_module)
            return None, "asserted" if rail_cfg.enabled else "held off"

        narrate_step(logger, describe_high_current_rail(rail_cfg), _build_rail)

    i2c_cfg = config.i2c
    if i2c is None:
        if i2c_cfg is not None and not i2c_cfg.enabled:
            narrate_skip(logger, describe_i2c(i2c_cfg), "disabled")
        else:

            def _build_i2c() -> tuple[busio.I2C | None, str]:
                bus = _setup_i2c(i2c_cfg, board_module)
                return bus, "no bus" if bus is None else "ok"

            i2c = narrate_step(logger, describe_i2c(i2c_cfg), _build_i2c)

    spi_cfg = config.spi
    if spi_cfg is not None and not spi_cfg.enabled:
        narrate_skip(logger, describe_spi(spi_cfg), "disabled")
        spi = None
    else:
        spi = narrate_step(
            logger, describe_spi(spi_cfg), lambda: (_setup_spi(spi_cfg, board_module), "ok")
        )

    if config.neopixel_current_budget is not None:
        logger.log(describe_neopixel_current_budget(config.neopixel_current_budget))

    outputs: list[EffectOutput] = []
    for index, pixels_cfg in enumerate(config.pixels):
        if not pixels_cfg.enabled:
            narrate_skip(logger, describe_pixel_entry(index, pixels_cfg), "disabled")
            continue
        outputs.extend(
            narrate_step(
                logger,
                describe_pixel_entry(index, pixels_cfg),
                lambda pixels_cfg=pixels_cfg: (_setup_pixels(pixels_cfg, board_module, i2c), "ok"),
            )
        )

    def _build_buttons() -> tuple[DebouncedButtons, str]:
        button_pins = [
            _resolve_pin(board_module, f"buttons[{i}]", name)
            for i, name in enumerate(config.buttons)
        ]
        return _setup_buttons(*button_pins), "ok"

    buttons = narrate_step(logger, describe_buttons(config.buttons), _build_buttons)

    accelerometer = None
    if config.accelerometer is not None:
        accelerometer_cfg = config.accelerometer
        description = describe_accelerometer(accelerometer_cfg)
        if accelerometer_cfg.enabled:
            accelerometer = narrate_step(
                logger,
                description,
                lambda: (
                    _setup_accelerometer(
                        _require_i2c(i2c, "accelerometer"), accelerometer_cfg.address
                    ),
                    "ok",
                ),
            )
        else:
            narrate_skip(logger, description, "disabled")

    magnetometer = None
    if config.magnetometer is not None:
        magnetometer_cfg = config.magnetometer
        description = describe_magnetometer(magnetometer_cfg)
        if magnetometer_cfg.enabled:
            magnetometer = narrate_step(
                logger,
                description,
                lambda: (
                    _setup_magnetometer(
                        _require_i2c(i2c, "magnetometer"), magnetometer_cfg.address
                    ),
                    "ok",
                ),
            )
        else:
            narrate_skip(logger, description, "disabled")

    audio_cfg = config.audio
    audio_registry: AudioRegistry | None = None
    if audio_cfg is not None:
        if not audio_cfg.enabled:
            narrate_skip(logger, describe_audio(audio_cfg), "disabled")
        else:

            def _build_audio() -> tuple[tuple[AudioRegistry, EffectOutput], str]:
                registry = AudioRegistry()
                return (registry, _setup_audio(audio_cfg, board_module, registry)), "ok"

            audio_registry, audio_output = narrate_step(
                logger, describe_audio(audio_cfg), _build_audio
            )
            outputs.append(audio_output)

    if config.haptics is not None:
        haptics_cfg = config.haptics
        description = describe_haptics(haptics_cfg)
        if haptics_cfg.enabled:

            def _build_haptics() -> tuple[EffectOutput, str]:
                driver = _setup_drv2605(_require_i2c(i2c, "haptics"), haptics_cfg.address)
                # Drv2605EffectOutput's own module imports adafruit_drv2605 at load
                # time, so this import is deferred here — reached only once
                # _setup_drv2605 has already confirmed the library is importable.
                from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

                return Drv2605EffectOutput(driver), "ok"

            outputs.append(narrate_step(logger, description, _build_haptics))
        else:
            narrate_skip(logger, description, "disabled")

    radio = None
    if config.radio is not None:
        radio_cfg = config.radio
        description = describe_radio(radio_cfg)
        if radio_cfg.enabled:
            radio = narrate_step(
                logger,
                description,
                lambda: (_setup_radio(_require_spi(spi, "radio"), radio_cfg, board_module), "ok"),
            )
        else:
            narrate_skip(logger, description, "disabled")

    storage = None
    if config.sdcard is not None:
        sdcard_cfg = config.sdcard
        description = describe_sdcard(sdcard_cfg)
        if sdcard_cfg.enabled:
            storage = narrate_step(
                logger,
                description,
                lambda: (
                    _setup_sdcard(_require_spi(spi, "sdcard"), sdcard_cfg, board_module),
                    "ok",
                ),
            )
        else:
            narrate_skip(logger, description, "disabled")

    ir: InfraredTransceiver | None = None
    if config.ir is not None:
        ir_cfg = config.ir
        description = describe_ir(ir_cfg)
        if ir_cfg.enabled:

            def _build_ir() -> tuple[InfraredTransceiver, str]:
                rx_pin_names = ir_cfg.rx
                if len(rx_pin_names) == 1:
                    rx_pins = [_resolve_pin(board_module, "ir.rx", rx_pin_names[0])]
                else:
                    rx_pins = [
                        _resolve_pin(board_module, f"ir.rx[{i}]", name)
                        for i, name in enumerate(rx_pin_names)
                    ]

                emitter_pins: dict[str, microcontroller.Pin] = {}
                for emitter_key, pin_name in ir_cfg.emitters.items():
                    emitter_pins[emitter_key] = _resolve_pin(
                        board_module, f"ir.{emitter_key}", pin_name
                    )

                transceiver, writer_kind = _setup_ir(rx_pins, emitter_pins)
                suffix = f"writer={writer_kind} ok" if writer_kind is not None else "ok"
                return transceiver, suffix

            ir = narrate_step(logger, description, _build_ir)
        else:
            narrate_skip(logger, description, "disabled")

    hardware_network_controls = HardwareNetworkControls(ir, radio=radio)

    elapsed = time.monotonic() - start
    logger.log(
        f"ready outputs={len(outputs)} buttons={len(config.buttons)} elapsed_s={elapsed:.3f}"
    )

    return DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=hardware_network_controls,
        ir=ir,
        radio=radio,
        storage=storage,
        audio_registry=audio_registry,
    )
