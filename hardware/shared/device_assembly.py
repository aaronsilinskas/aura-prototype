"""Device assembly — the one board-free turning of a ``DeviceConfig`` into ``DeviceHardware``.

Decides what a config builds and reaches hardware only through a
:class:`~hardware.shared.device_parts.DeviceParts` adapter, so the physical
device and the Simulated device build, skip, reject and narrate a config alike.

Every component is config-gated: built only when its section is declared *and*
enabled, never probed by physical presence. The high-current rail is the one
exception: a disabled rail is still driven, to its deasserted level.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    GatedSection = TypeVar("GatedSection", bound="_Gated")
    T = TypeVar("T")
except ImportError:
    pass

import time

from engine.capabilities import IR_RECEIVE, button_capability, ir_emitter_capability
from engine.effects.output import EffectOutput
from engine.input import AccelerationData, MagneticData
from engine.log import Logger
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
    I2CConfig,
    I2CDeviceConfig,
    IRConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    RadioConfig,
    SDCardConfig,
    SPIConfig,
)
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_parts import DeviceParts
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.polled_part import PolledPart
from hardware.shared.polled_sensor import PolledSensor
from hardware.shared.radio_transceiver import RadioTransceiver

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Protocol

    from hardware.shared.device_parts import Bus

    class _Gated(Protocol):
        """A config section ``_gated_step`` can skip: one with an ``enabled`` flag."""

        @property
        def enabled(self) -> bool: ...


__all__ = ["assemble_device", "button_label", "open_i2c"]


def button_label(index: int) -> str:
    """The label of the button declared at *index*: ``A``, ``B``, … in declaration order."""
    return chr(ord("A") + index)


def open_i2c(name: str, declared: dict[str, I2CConfig], parts: DeviceParts) -> Bus | None:
    """Open I2C bus *name*: its declared pins, or the board's own bus when undeclared.

    ``None`` when the bus can't be built (nothing pulls it up).
    """
    i2c = declared.get(name)
    if i2c is None:
        return parts.i2c_bus(None, None)
    return parts.i2c_bus(i2c.scl, i2c.sda)


def _require_i2c(
    buses: dict[str, Bus | None], section: str, device: MatrixPixelsConfig | I2CDeviceConfig
) -> Bus:
    bus = buses.get(device.i2c)
    if bus is None:
        raise RuntimeError(f"{section} joins I2C bus '{device.i2c}' but no I2C bus is available")
    return bus


def _open_named_buses(
    logger: Logger,
    names: list[str],
    describe: Callable[[str], str],
    open_bus: Callable[[str], Bus | None],
) -> dict[str, Bus | None]:
    """Open each **Named bus** in *names* once, in first-named order, one narrated line each.

    *names* holds the bus each enabled device joins, so a declared bus no
    enabled device names is never opened. A bus *open_bus* can't build is
    ``None``, narrated ``no bus``; the device that needs it rejects it.
    """
    buses: dict[str, Bus | None] = {}
    for name in names:
        if name in buses:
            continue

        def _build(name: str = name) -> tuple[Bus | None, str]:
            bus = open_bus(name)
            return bus, "no bus" if bus is None else "ok"

        buses[name] = narrate_step(logger, describe(name), _build)
    return buses


def _open_spi(name: str, declared: dict[str, SPIConfig], parts: DeviceParts) -> Bus | None:
    """Open SPI bus *name*: its declared pins, or the board's own bus when undeclared."""
    spi = declared.get(name)
    if spi is None:
        return parts.spi_bus(None, None, None)
    return parts.spi_bus(spi.sck, spi.mosi, spi.miso)


def _require_spi(
    buses: dict[str, Bus | None], section: str, device: RadioConfig | SDCardConfig
) -> Bus:
    bus = buses.get(device.spi)
    if bus is None:
        raise RuntimeError(f"{section} joins SPI bus '{device.spi}' but no SPI bus is available")
    return bus


def _pixel_outputs(
    index: int,
    pixels: MatrixPixelsConfig | NeoPixelPixelsConfig,
    parts: DeviceParts,
    i2c: dict[str, Bus | None],
) -> list[EffectOutput]:
    """Build enabled pixel entry *index*: a matrix, or one output per NeoPixel strip."""
    if isinstance(pixels, MatrixPixelsConfig):
        bus = _require_i2c(i2c, f"pixels[{index}]", pixels)
        return [parts.matrix_pixels(pixels, bus)]
    return [parts.neopixel_strip(strip, strip.pin) for strip in pixels.strips]


def _ir(ir_config: IRConfig, parts: DeviceParts) -> tuple[InfraredTransceiver, str]:
    """Wire the IR subsystem; return it with the ``ir`` line's closing suffix."""
    readers = [parts.ir_reader(pin) for pin in ir_config.rx]
    transceiver = InfraredTransceiver(readers, ir_config.emitters, parts.ir_writer)
    writer_kind = transceiver.writer_kind
    return transceiver, "ok" if writer_kind is None else f"writer={writer_kind} ok"


def _gated_step(
    logger: Logger,
    section: GatedSection | None,
    describe: Callable[[GatedSection], str],
    build: Callable[[GatedSection], tuple[T, str]],
) -> T | None:
    """Narrate and *build* a declared, enabled *section*; ``None`` for an absent or disabled one.

    *build* returns the built value and the suffix closing its line.
    """
    if section is None:
        return None
    description = describe(section)
    if not section.enabled:
        narrate_skip(logger, description, "disabled")
        return None
    return narrate_step(logger, description, lambda: build(section))


def _polled_sensor(
    logger: Logger,
    i2c: dict[str, Bus | None],
    name: str,
    section: I2CDeviceConfig | None,
    describe: Callable[[I2CDeviceConfig], str],
    read_part: Callable[[I2CDeviceConfig, Bus], Callable[[], tuple[float, float, float]]],
    reading: AccelerationData | MagneticData,
) -> PolledSensor | None:
    """Build the I2C sensor ``name`` as a **PolledSensor** over ``reading``, gated like any section.

    ``read_part`` is the ``DeviceParts`` method building its raw read; the
    sensor's I2C bus must be open.
    """
    return _gated_step(
        logger,
        section,
        describe,
        lambda c: (
            PolledSensor(read_part(c, _require_i2c(i2c, name, c)), reading, name, logger),
            "ok",
        ),
    )


def _append_built(polled: list[PolledPart], part: PolledPart | None) -> None:
    """List ``part`` as a **Polled part** if it was built; an absent part is never polled."""
    if part is not None:
        polled.append(part)


def _capabilities(
    buttons: DebouncedButtons,
    accelerometer: PolledSensor | None,
    magnetometer: PolledSensor | None,
    radio: RadioTransceiver | None,
    storage: DeviceStorage | None,
    ir: InfraredTransceiver | None,
) -> frozenset[str]:
    """The **Capabilities** of what was built; a part that is ``None`` contributes nothing.

    Read off the built parts, never the config, so a declared component that
    was not built is never counted.
    """
    names = [button_capability(label) for label in buttons.labels()]
    for name, part in (
        ("accelerometer", accelerometer),
        ("magnetometer", magnetometer),
        ("radio", radio),
        ("storage", storage),
    ):
        if part is not None:
            names.append(name)
    if ir is not None:
        names.extend(ir_emitter_capability(emitter) for emitter in ir.emitters)
        if ir.receives:
            names.append(IR_RECEIVE)
    return frozenset(names)


def assemble_device(
    config: DeviceConfig,
    parts: DeviceParts,
    logger: Logger | None = None,
) -> DeviceHardware:
    """Build *config*'s hardware through *parts*, narrating each step to *logger*.

    Components come up in a fixed order: high-current rail, buses, pixels,
    buttons, sensors, audio, haptics, radio, storage, IR. Each narrates one
    line opened before it is built (see
    :func:`~hardware.shared.build_narration.narrate_step`), so a part that
    raises fails its own line and the exception propagates. *logger* omitted
    means silent.

    I2C and SPI buses open on demand: only a **Named bus** an enabled device
    joins is opened, once, and every device joining it gets that same bus.

    Raises:
        RuntimeError: If an enabled section's bus is unavailable: its I2C bus
            could not be built, or the board has no SPI bus of its own for an
            undeclared ``default``.
    """
    if logger is None:
        logger = Logger.SILENT

    start = time.monotonic()
    logger.log(f"begin board={parts.board_name()}")

    rail = config.high_current_rail
    if rail is not None:

        def _build_rail() -> tuple[None, str]:
            level = rail.active_high if rail.enabled else not rail.active_high
            parts.high_current_rail(rail.pin, level)
            return None, "asserted" if rail.enabled else "held off"

        narrate_step(logger, describe_high_current_rail(rail), _build_rail)

    i2c = _open_named_buses(
        logger,
        [d.i2c for d in config.i2c_devices()],
        lambda name: describe_i2c(name, config.i2c.get(name)),
        lambda name: open_i2c(name, config.i2c, parts),
    )

    spi = _open_named_buses(
        logger,
        [d.spi for d in config.spi_devices()],
        lambda name: describe_spi(name, config.spi.get(name)),
        lambda name: _open_spi(name, config.spi, parts),
    )

    if config.neopixel_current_budget is not None:
        logger.log(describe_neopixel_current_budget(config.neopixel_current_budget))

    outputs: list[EffectOutput] = []
    for index, pixels in enumerate(config.pixels):
        description = describe_pixel_entry(index, pixels)
        if not pixels.enabled:
            narrate_skip(logger, description, "disabled")
            continue

        def _build_pixels(
            index: int = index, pixels: MatrixPixelsConfig | NeoPixelPixelsConfig = pixels
        ) -> tuple[list[EffectOutput], str]:
            return _pixel_outputs(index, pixels, parts, i2c), "ok"

        outputs.extend(narrate_step(logger, description, _build_pixels))

    def _build_buttons() -> tuple[DebouncedButtons, str]:
        readers = [
            (button_label(i), parts.button_reader(pin)) for i, pin in enumerate(config.buttons)
        ]
        return DebouncedButtons(readers), "ok"

    buttons = narrate_step(logger, describe_buttons(config.buttons), _build_buttons)
    polled: list[PolledPart] = [buttons]

    accelerometer = _polled_sensor(
        logger,
        i2c,
        "accelerometer",
        config.accelerometer,
        describe_accelerometer,
        parts.accelerometer,
        AccelerationData(0.0, 0.0, 0.0),
    )
    magnetometer = _polled_sensor(
        logger,
        i2c,
        "magnetometer",
        config.magnetometer,
        describe_magnetometer,
        parts.magnetometer,
        MagneticData(0.0, 0.0, 0.0),
    )
    _append_built(polled, accelerometer)
    _append_built(polled, magnetometer)

    def _build_audio(audio: AudioConfig) -> tuple[EffectOutput, str]:
        output = parts.audio_output(
            audio, audio.i2s_bit_clock, audio.i2s_word_select, audio.i2s_data
        )
        return output, "ok"

    audio_output = _gated_step(logger, config.audio, describe_audio, _build_audio)
    if audio_output is not None:
        outputs.append(audio_output)

    haptic_output = _gated_step(
        logger,
        config.haptics,
        describe_haptics,
        lambda c: (parts.haptic_output(c, _require_i2c(i2c, "haptics", c)), "ok"),
    )
    if haptic_output is not None:
        outputs.append(haptic_output)

    def _build_radio(radio: RadioConfig) -> tuple[RadioTransceiver, str]:
        transport = parts.radio_transport(
            radio,
            _require_spi(spi, "radio", radio),
            radio.cs,
            radio.reset,
        )
        return RadioTransceiver(transport), "ok"

    radio = _gated_step(logger, config.radio, describe_radio, _build_radio)
    _append_built(polled, radio)

    storage = _gated_step(
        logger,
        config.sdcard,
        describe_sdcard,
        lambda c: (
            parts.storage(c, _require_spi(spi, "sdcard", c), c.cs),
            "ok",
        ),
    )

    ir = _gated_step(logger, config.ir, describe_ir, lambda c: _ir(c, parts))
    _append_built(polled, ir)

    elapsed = time.monotonic() - start
    logger.log(
        f"ready outputs={len(outputs)} buttons={len(config.buttons)} elapsed_s={elapsed:.3f}"
    )

    return DeviceHardware(
        capabilities=_capabilities(buttons, accelerometer, magnetometer, radio, storage, ir),
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=HardwareNetworkControls(ir, radio=radio),
        ir=ir,
        radio=radio,
        storage=storage,
        polled=tuple(polled),
    )
