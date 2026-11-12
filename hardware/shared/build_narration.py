"""Board-free "open a line, run the build, close it" narration primitive.

A component builder narrating its own construction to a :class:`~engine.log.Logger`
otherwise hand-threads the same three calls every time: ``begin`` a line describing
what it is about to build, run the build, then ``end`` the line with a success detail
or ``fail`` it on an exception. :func:`narrate_step` and :func:`narrate_skip` own that
sequence once so a component block reduces to a single call.

The ``describe_*`` functions build each boot step's description. Every one works
from a config section's pin-name strings, never resolved pins, so a step's line
opens before any of its pins resolve -- and a bad pin name fails that step's own
line. Each returns the exact line the board prints for its section, so a
section that narrates a bare name when disabled (``audio``,
``pixels[i] <kind>``) gets that form here too; the rest keep their detail.

No ``board``/``busio`` imports, so this module is CPython-testable in isolation,
like the rest of ``hardware/shared``.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

from engine.log import Logger
from engine.network import IR_EMITTERS
from hardware.shared.device_config import (
    DEFAULT_BUS,
    AudioConfig,
    HighCurrentRailConfig,
    I2CConfig,
    I2CDeviceConfig,
    IRConfig,
    MatrixPixelsConfig,
    NeoPixelCurrentBudgetConfig,
    NeoPixelPixelsConfig,
    PinRef,
    RadioConfig,
    SDCardConfig,
    SPIConfig,
)

__all__ = [
    "describe_accelerometer",
    "describe_audio",
    "describe_buttons",
    "describe_haptics",
    "describe_high_current_rail",
    "describe_i2c",
    "describe_ir",
    "describe_magnetometer",
    "describe_neopixel_current_budget",
    "describe_pixel_entry",
    "describe_radio",
    "describe_sdcard",
    "describe_spi",
    "narrate_skip",
    "narrate_step",
]


def narrate_step(
    logger: Logger,
    description: str,
    build: Callable[[], tuple[T, str]],
) -> T:
    """Narrate one build step: open, build, close — or fail and re-raise.

    Opens *logger*'s line with *description* **before** calling *build*, so a
    failure inside *build* (e.g. resolving an unknown pin) always closes this
    step's own line rather than one already closed by a neighbouring step.
    *build* returns a ``(value, suffix)`` pair: *suffix* closes the line and
    *value* is returned to the caller. If *build* raises, the line is closed
    with ``FAILED`` and the exception propagates unchanged.

    Trusts *logger* is a real :class:`~engine.log.Logger` — a caller that
    accepts an optional logger owns normalizing ``None`` to
    :data:`~engine.log.Logger.SILENT` before calling this.
    """
    logger.begin(description)
    try:
        value, suffix = build()
    except Exception:
        logger.fail()
        raise
    logger.end(suffix)
    return value


def narrate_skip(logger: Logger, description: str, note: str) -> None:
    """Narrate a step with no build: open the line, close it with *note*.

    For a disabled or otherwise not-built component.
    """
    logger.begin(description)
    logger.end(note)


def describe_high_current_rail(rail: HighCurrentRailConfig) -> str:
    return f"high_current_rail pin={rail.pin.name} active_high={rail.active_high}"


def describe_i2c(name: str, i2c: I2CConfig | None) -> str:
    """Describe opening the I2C bus *name*; *i2c* ``None`` is the board's own bus."""
    if i2c is None:
        return f"i2c {name} board"
    return f"i2c {name} scl={i2c.scl.name} sda={i2c.sda.name}"


def describe_spi(name: str, spi: SPIConfig | None) -> str:
    """Describe opening the SPI bus *name*; *spi* ``None`` is the board's own bus."""
    if spi is None:
        return f"spi {name} board"
    return f"spi {name} sck={spi.sck.name} mosi={spi.mosi.name} miso={spi.miso.name}"


def describe_neopixel_current_budget(budget: NeoPixelCurrentBudgetConfig) -> str:
    """Return the line reporting what the parse-time current budget applied.

    The tuning already happened in ``parse_device_config``; this only reports
    it, so each ``pixels[i]`` line's ``brightness=`` reads as the tuned value.
    """
    return (
        f"neopixel_current_budget limit={budget.current_limit_ma}mA "
        + f"estimate={budget.estimate_ma:.0f}mA scale={budget.scale:.2f} "
        + f"at_min_brightness={budget.at_min_brightness}"
    )


def _format_ranges(ranges: dict[str, range]) -> str:
    """Format a scope-key -> range mapping as ``"key:start-stop"`` pairs, e.g.
    a matrix's ``scope_rows`` or a NeoPixel strip's ``scope_pixels``."""
    return " ".join(f"{key}:{r.start}-{r.stop}" for key, r in ranges.items())


def _address_suffix(address: int | None) -> str:
    """Return `` address=0xNN`` for a configured override, or ``""`` when there is none."""
    return f" address=0x{address:02X}" if address is not None else ""


def _describe_i2c_chip(part: str, chip: str, config: I2CDeviceConfig) -> str:
    """Describe an I2C ``part`` by its ``chip``, with its configured address and bus."""
    return f"{part} {chip}" + _address_suffix(config.address) + _bus_suffix("i2c", config.i2c)


def _bus_suffix(kind: str, name: str) -> str:
    return f" {kind}={name}" if name != DEFAULT_BUS else ""


def _describe_neopixel_pixels(pixels: NeoPixelPixelsConfig) -> str:
    """Return the pin/count/order/segmentation/brightness detail for a NeoPixel entry's strip."""
    strip = pixels.strips[0]
    return (
        f"pin={strip.pin.name} count={strip.count} order={strip.order} "
        + f"scope_pixels=[{_format_ranges(strip.scope_pixels)}] "
        + f"brightness={strip.brightness:.2f}"
    )


def describe_pixel_entry(index: int, pixels: MatrixPixelsConfig | NeoPixelPixelsConfig) -> str:
    kind = "matrix" if isinstance(pixels, MatrixPixelsConfig) else "neopixel"
    if not pixels.enabled:
        return f"pixels[{index}] {kind}"
    if isinstance(pixels, MatrixPixelsConfig):
        detail = (
            f"cols={pixels.cols} scope_rows=[{_format_ranges(pixels.scope_rows)}] "
            + f"brightness={pixels.brightness:.2f}"
            + _address_suffix(pixels.address)
            + _bus_suffix("i2c", pixels.i2c)
        )
    else:
        detail = _describe_neopixel_pixels(pixels)
    return f"pixels[{index}] {kind} {detail}"


def describe_buttons(pins: list[PinRef]) -> str:
    """Label buttons ``A``, ``B``, ... in declaration order -- the labels the board assigns."""
    labelled = " ".join(f"{chr(ord('A') + i)}={pin.name}" for i, pin in enumerate(pins))
    return f"buttons {labelled}" if labelled else "buttons"


def describe_accelerometer(accelerometer: I2CDeviceConfig) -> str:
    return _describe_i2c_chip("accelerometer", "lis3dh", accelerometer)


def describe_magnetometer(magnetometer: I2CDeviceConfig) -> str:
    return _describe_i2c_chip("magnetometer", "mmc5603", magnetometer)


def describe_haptics(haptics: I2CDeviceConfig) -> str:
    return _describe_i2c_chip("haptics", "drv2605", haptics)


def describe_audio(audio: AudioConfig) -> str:
    if not audio.enabled:
        return "audio"
    return (
        f"audio voices={audio.voices} max_volume={audio.max_volume:.2f} "
        + f"i2s_bit_clock={audio.i2s_bit_clock.name} "
        + f"i2s_word_select={audio.i2s_word_select.name} i2s_data={audio.i2s_data.name}"
    )


def describe_radio(radio: RadioConfig) -> str:
    return (
        f"radio frequency={radio.frequency} node={radio.node} "
        + f"cs={radio.cs.name} reset={radio.reset.name}"
        + _bus_suffix("spi", radio.spi)
    )


def describe_sdcard(sdcard: SDCardConfig) -> str:
    return f"sdcard mount={sdcard.mount} cs={sdcard.cs.name}" + _bus_suffix("spi", sdcard.spi)


def describe_ir(ir: IRConfig) -> str:
    """Describe the ``ir`` step without its writer kind (``writer=pio``/``pulseio``),
    which is only known once the IR subsystem is built, so it closes the line instead."""
    rx_desc = f"rx=[{' '.join(ir.rx)}]" if ir.rx else "rx=(none)"
    if len(ir.rx) > 1:
        rx_desc += " (IR multi-receiver)"
    if ir.emitters:
        emitters_desc = "emitters=" + " ".join(
            f"{key}:{ir.emitters[key]}" for key in IR_EMITTERS if key in ir.emitters
        )
    else:
        emitters_desc = "emitters=(none)"
    return f"ir {rx_desc} {emitters_desc}"
