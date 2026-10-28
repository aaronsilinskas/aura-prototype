"""Board-free "open a line, run the build, close it" narration primitive.

A component builder narrating its own construction to a :class:`~engine.log.Logger`
otherwise hand-threads the same three calls every time: ``begin`` a line describing
what it is about to build, run the build, then ``end`` the line with a success detail
or ``fail`` it on an exception. :func:`narrate_step` and :func:`narrate_skip` own that
sequence once so a component block reduces to a single call.

The ``describe_*`` functions build each boot step's description. Every one works
from a config section's pin-name strings, never resolved pins, so a step's line
opens before any of its pins resolve -- and a bad pin name fails that step's own
line.

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
    AudioConfig,
    HighCurrentRailConfig,
    I2CConfig,
    I2CDeviceConfig,
    IRConfig,
    MatrixPixelsConfig,
    NeoPixelCurrentBudgetConfig,
    NeoPixelPixelsConfig,
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
    """Return the ``high_current_rail`` step's description."""
    return f"high_current_rail pin={rail.pin} active_high={rail.active_high}"


def describe_i2c(i2c: I2CConfig | None) -> str:
    """Return the ``i2c`` step's description: the configured pins, ``default``
    for no section (the board's own SCL/SDA), or bare ``i2c`` when disabled."""
    if i2c is None:
        return "i2c default"
    if not i2c.enabled:
        return "i2c"
    return f"i2c scl={i2c.scl} sda={i2c.sda}"


def describe_spi(spi: SPIConfig | None) -> str:
    """Return the ``spi`` step's description: the configured pins, ``default``
    for no section (the board's own SPI bus), or bare ``spi`` when disabled."""
    if spi is None:
        return "spi default"
    if not spi.enabled:
        return "spi"
    return f"spi sck={spi.sck} mosi={spi.mosi} miso={spi.miso}"


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
    """Return `` address=0xNN`` for a configured override, or `""` when *address* is `None`.

    Shared by every description that documents an I2C device's optional
    address override (the matrix pixel entry and the
    accelerometer/magnetometer/haptics sections).
    """
    return f" address=0x{address:02X}" if address is not None else ""


def _describe_neopixel_pixels(pixels: NeoPixelPixelsConfig) -> str:
    """Return the pin/count/order/segmentation/brightness detail for a NeoPixel
    entry -- the ``strips`` form (one physical strip, segmented by
    ``scope_pixels``) or the legacy ``scopes`` map form (one physical strip
    per scope key, joined with ``" | "`` when more than one shares the entry).
    """
    if pixels.strips:
        strip = pixels.strips[0]
        return (
            f"pin={strip.pin} count={strip.count} order={strip.order} "
            + f"scope_pixels=[{_format_ranges(strip.scope_pixels)}] "
            + f"brightness={strip.brightness:.2f}"
        )
    return " | ".join(
        f"pin={scope.pin} count={scope.count} order={scope.order} scope={key} "
        + f"brightness={scope.brightness:.2f}"
        for key, scope in pixels.scopes.items()
    )


def describe_pixel_entry(index: int, pixels: MatrixPixelsConfig | NeoPixelPixelsConfig) -> str:
    """Return the ``pixels[index]`` step's description, or just its index and
    kind (``matrix``/``neopixel``) when the entry is disabled."""
    kind = "matrix" if isinstance(pixels, MatrixPixelsConfig) else "neopixel"
    if not pixels.enabled:
        return f"pixels[{index}] {kind}"
    if isinstance(pixels, MatrixPixelsConfig):
        detail = (
            f"cols={pixels.cols} scope_rows=[{_format_ranges(pixels.scope_rows)}] "
            + f"brightness={pixels.brightness:.2f}"
            + _address_suffix(pixels.address)
        )
    else:
        detail = _describe_neopixel_pixels(pixels)
    return f"pixels[{index}] {kind} {detail}"


def describe_buttons(pin_names: list[str]) -> str:
    """Return the ``buttons`` step's description, pairing each button's label
    (``A``, ``B``, ...) with its declared pin name, e.g. ``buttons A=GP2 B=GP3``."""
    labelled = " ".join(f"{chr(ord('A') + i)}={name}" for i, name in enumerate(pin_names))
    return f"buttons {labelled}" if labelled else "buttons"


def describe_accelerometer(accelerometer: I2CDeviceConfig) -> str:
    """Return the ``accelerometer`` step's description."""
    return "accelerometer lis3dh" + _address_suffix(accelerometer.address)


def describe_magnetometer(magnetometer: I2CDeviceConfig) -> str:
    """Return the ``magnetometer`` step's description."""
    return "magnetometer mmc5603" + _address_suffix(magnetometer.address)


def describe_haptics(haptics: I2CDeviceConfig) -> str:
    """Return the ``haptics`` step's description."""
    return "haptics drv2605" + _address_suffix(haptics.address)


def describe_audio(audio: AudioConfig) -> str:
    """Return the ``audio`` step's description, or bare ``audio`` when disabled."""
    if not audio.enabled:
        return "audio"
    return (
        f"audio voices={audio.voices} max_volume={audio.max_volume:.2f} "
        + f"i2s_bit_clock={audio.i2s_bit_clock} "
        + f"i2s_word_select={audio.i2s_word_select} i2s_data={audio.i2s_data}"
    )


def describe_radio(radio: RadioConfig) -> str:
    """Return the ``radio`` step's description."""
    return (
        f"radio frequency={radio.frequency} node={radio.node} "
        + f"cs={radio.cs} reset={radio.reset}"
    )


def describe_sdcard(sdcard: SDCardConfig) -> str:
    """Return the ``sdcard`` step's description."""
    return f"sdcard mount={sdcard.mount} cs={sdcard.cs}"


def describe_ir(ir: IRConfig) -> str:
    """Return the ``ir`` step's description: its rx pins and wired emitters.

    Two or more rx pins append the **IR multi-receiver** label (see
    GLOSSARY.md), selected purely by pin count. Emitters are listed
    ``key:pin`` in ``IR_EMITTERS`` order -- the order transmitters are wired
    in, independent of the config's own key order -- or ``(none)``.

    The writer kind (``writer=pio``/``writer=pulseio``) is not part of this:
    it is only known once the IR subsystem is built, so it closes the line.
    """
    rx_desc = f"rx=[{' '.join(ir.rx)}]"
    if len(ir.rx) > 1:
        rx_desc += " (IR multi-receiver)"
    if ir.emitters:
        emitters_desc = "emitters=" + " ".join(
            f"{key}:{ir.emitters[key]}" for key in IR_EMITTERS if key in ir.emitters
        )
    else:
        emitters_desc = "emitters=(none)"
    return f"ir {rx_desc} {emitters_desc}"
