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

    Section = TypeVar("Section")
    T = TypeVar("T")
except ImportError:
    pass

import time

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
    IRConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    NeoPixelStripConfig,
    RadioConfig,
)
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_parts import DeviceParts, PinRef
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_wiring import wire_ir
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.polled_sensor import PolledSensor
from hardware.shared.radio_transceiver import RadioTransceiver

__all__ = ["assemble_device", "button_label", "open_i2c"]


def button_label(index: int) -> str:
    """The label of the button declared at *index*: ``A``, ``B``, … in declaration order."""
    return chr(ord("A") + index)


def open_i2c(i2c_config: I2CConfig | None, parts: DeviceParts) -> object | None:
    """Return the I2C bus *i2c_config* asks for: ``None`` when it is disabled or none can be built.

    An absent section means the board's default pins.
    """
    if i2c_config is None:
        return parts.i2c_bus(None, None)
    if not i2c_config.enabled:
        return None
    return parts.i2c_bus(PinRef(i2c_config.scl, "i2c.scl"), PinRef(i2c_config.sda, "i2c.sda"))


def _require_i2c(i2c: object | None, section: str) -> object:
    if i2c is None:
        raise RuntimeError(f"{section} section is declared but no I2C bus is available")
    return i2c


def _require_spi(spi: object | None, section: str) -> object:
    if spi is None:
        raise RuntimeError(f"{section} section is declared but no SPI bus is available")
    return spi


def _pixel_outputs(
    pixels: MatrixPixelsConfig | NeoPixelPixelsConfig, parts: DeviceParts, i2c: object | None
) -> list[EffectOutput]:
    """Build one enabled pixel entry: a matrix, or one output per NeoPixel strip.

    A legacy ``scopes`` entry is one strip per scope, spanning the whole scope.
    """
    if isinstance(pixels, MatrixPixelsConfig):
        if i2c is None:
            raise RuntimeError("pixels.type is 'matrix' but no I2C bus is available")
        return [parts.matrix_pixels(pixels, i2c)]
    outputs = [
        parts.neopixel_strip(strip, PinRef(strip.pin, "pixels.pin")) for strip in pixels.strips
    ]
    for key, scope in pixels.scopes.items():
        strip = NeoPixelStripConfig(
            scope.pin, scope.count, scope.order, scope.brightness, {key: range(0, scope.count)}
        )
        outputs.append(parts.neopixel_strip(strip, PinRef(scope.pin, f"pixels.scopes.{key}.pin")))
    return outputs


def _ir(ir_config: IRConfig, parts: DeviceParts) -> tuple[InfraredTransceiver, str]:
    """Wire the IR subsystem; return it with the ``ir`` line's closing suffix."""
    rx = ir_config.rx
    if len(rx) == 1:
        rx_pins = [PinRef(rx[0], "ir.rx")]
    else:
        rx_pins = [PinRef(name, f"ir.rx[{i}]") for i, name in enumerate(rx)]
    readers = [parts.ir_reader(pin) for pin in rx_pins]
    emitter_pins = {
        emitter: PinRef(name, f"ir.{emitter}") for emitter, name in ir_config.emitters.items()
    }
    transceiver, writer_kind = wire_ir(readers, emitter_pins, parts.ir_writer)
    return transceiver, "ok" if writer_kind is None else f"writer={writer_kind} ok"


def _gated_step(
    logger: Logger,
    section: Section | None,
    describe: Callable[[Section], str],
    build: Callable[[Section], tuple[T, str]],
) -> T | None:
    """Narrate and *build* a declared, enabled *section*; ``None`` for an absent or disabled one.

    *build* returns the built value and the suffix closing its line.
    """
    if section is None:
        return None
    description = describe(section)
    if not section.enabled:  # type: ignore[attr-defined]  # every gated section has one
        narrate_skip(logger, description, "disabled")
        return None
    return narrate_step(logger, description, lambda: build(section))


def assemble_device(
    config: DeviceConfig, parts: DeviceParts, logger: Logger | None = None
) -> DeviceHardware:
    """Build *config*'s hardware through *parts*, narrating each step to *logger*.

    Components come up in a fixed order: high-current rail, buses, pixels,
    buttons, sensors, audio, haptics, radio, storage, IR. Each narrates one
    line opened before it is built (see
    :func:`~hardware.shared.build_narration.narrate_step`), so a part that
    raises fails its own line and the exception propagates. *logger* omitted
    means silent.

    Raises:
        RuntimeError: If an enabled section needs an I2C or SPI bus and there
            is none: the bus is disabled, or no I2C bus could be built.
    """
    if logger is None:
        logger = Logger.SILENT

    start = time.monotonic()
    logger.log(f"begin board={parts.board_name()}")

    rail = config.high_current_rail
    if rail is not None:

        def _build_rail() -> tuple[None, str]:
            level = rail.active_high if rail.enabled else not rail.active_high
            parts.high_current_rail(PinRef(rail.pin, "high_current_rail.pin"), level)
            return None, "asserted" if rail.enabled else "held off"

        narrate_step(logger, describe_high_current_rail(rail), _build_rail)

    i2c_config = config.i2c
    i2c: object | None = None
    if i2c_config is not None and not i2c_config.enabled:
        narrate_skip(logger, describe_i2c(i2c_config), "disabled")
    else:

        def _build_i2c() -> tuple[object | None, str]:
            bus = open_i2c(i2c_config, parts)
            return bus, "no bus" if bus is None else "ok"

        i2c = narrate_step(logger, describe_i2c(i2c_config), _build_i2c)

    spi_config = config.spi
    spi: object | None = None
    if spi_config is not None and not spi_config.enabled:
        narrate_skip(logger, describe_spi(spi_config), "disabled")
    else:

        def _build_spi() -> tuple[object, str]:
            if spi_config is None:
                return parts.spi_bus(None, None, None), "ok"
            bus = parts.spi_bus(
                PinRef(spi_config.sck, "spi.sck"),
                PinRef(spi_config.mosi, "spi.mosi"),
                PinRef(spi_config.miso, "spi.miso"),
            )
            return bus, "ok"

        spi = narrate_step(logger, describe_spi(spi_config), _build_spi)

    if config.neopixel_current_budget is not None:
        logger.log(describe_neopixel_current_budget(config.neopixel_current_budget))

    outputs: list[EffectOutput] = []
    for index, pixels in enumerate(config.pixels):
        description = describe_pixel_entry(index, pixels)
        if not pixels.enabled:
            narrate_skip(logger, description, "disabled")
            continue
        outputs.extend(
            narrate_step(
                logger,
                description,
                lambda pixels=pixels: (_pixel_outputs(pixels, parts, i2c), "ok"),
            )
        )

    def _build_buttons() -> tuple[DebouncedButtons, str]:
        readers = [
            (button_label(i), parts.button_reader(PinRef(name, f"buttons[{i}]")))
            for i, name in enumerate(config.buttons)
        ]
        return DebouncedButtons(readers), "ok"

    buttons = narrate_step(logger, describe_buttons(config.buttons), _build_buttons)

    accelerometer = _gated_step(
        logger,
        config.accelerometer,
        describe_accelerometer,
        lambda c: (
            PolledSensor(
                parts.accelerometer(c, _require_i2c(i2c, "accelerometer")),
                AccelerationData(0.0, 0.0, 0.0),
                "accelerometer",
                logger,
            ),
            "ok",
        ),
    )
    magnetometer = _gated_step(
        logger,
        config.magnetometer,
        describe_magnetometer,
        lambda c: (
            PolledSensor(
                parts.magnetometer(c, _require_i2c(i2c, "magnetometer")),
                MagneticData(0.0, 0.0, 0.0),
                "magnetometer",
                logger,
            ),
            "ok",
        ),
    )

    def _build_audio(audio: AudioConfig) -> tuple[EffectOutput, str]:
        output = parts.audio_output(
            audio,
            PinRef(audio.i2s_bit_clock, "audio.i2s_bit_clock"),
            PinRef(audio.i2s_word_select, "audio.i2s_word_select"),
            PinRef(audio.i2s_data, "audio.i2s_data"),
        )
        return output, "ok"

    audio_output = _gated_step(logger, config.audio, describe_audio, _build_audio)
    if audio_output is not None:
        outputs.append(audio_output)

    haptic_output = _gated_step(
        logger,
        config.haptics,
        describe_haptics,
        lambda c: (parts.haptic_output(c, _require_i2c(i2c, "haptics")), "ok"),
    )
    if haptic_output is not None:
        outputs.append(haptic_output)

    def _build_radio(radio: RadioConfig) -> tuple[RadioTransceiver, str]:
        transport = parts.radio_transport(
            radio,
            _require_spi(spi, "radio"),
            PinRef(radio.cs, "radio.cs"),
            PinRef(radio.reset, "radio.reset"),
        )
        return RadioTransceiver(transport), "ok"

    radio = _gated_step(logger, config.radio, describe_radio, _build_radio)

    storage = _gated_step(
        logger,
        config.sdcard,
        describe_sdcard,
        lambda c: (parts.storage(c, _require_spi(spi, "sdcard"), PinRef(c.cs, "sdcard.cs")), "ok"),
    )

    ir = _gated_step(logger, config.ir, describe_ir, lambda c: _ir(c, parts))

    elapsed = time.monotonic() - start
    logger.log(
        f"ready outputs={len(outputs)} buttons={len(config.buttons)} elapsed_s={elapsed:.3f}"
    )

    return DeviceHardware(
        outputs=outputs,
        buttons=buttons,
        accelerometer=accelerometer,
        magnetometer=magnetometer,
        network_controls=HardwareNetworkControls(ir, radio=radio),
        ir=ir,
        radio=radio,
        storage=storage,
    )
