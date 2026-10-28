"""CircuitPythonParts — the Device assembly's ``DeviceParts`` adapter on a CircuitPython board.

Deploy-watch only: imports board, busio and digitalio. Every per-part driver
library is imported inside the part that builds it, so a config that doesn't
need a part never requires its library to be installed.

The adapter only builds what it is asked for: every enabled/declared and
bus-requirement decision belongs to ``hardware.shared.device_assembly``.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TYPE_CHECKING, Final
except ImportError:
    TYPE_CHECKING = False

# Type-checker-only: the driver library is imported by the part that builds it.
if TYPE_CHECKING:
    from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

import time

import board
import busio
import digitalio
import microcontroller

from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.device_config import MatrixPixelsConfig, NeoPixelStripConfig
from hardware.shared.device_parts import DeviceParts, PinRef

__all__ = ["CircuitPythonParts"]


def _resolve_pin(board_module: object, field: str, name: str) -> microcontroller.Pin:
    try:
        return getattr(board_module, name)
    except AttributeError:
        raise ValueError(f"{field}: pin '{name}' not found on board") from None


_MATRIX_STARTUP_TIMEOUT_S: Final = 3


def _setup_matrix_is31fl3741(
    i2c: busio.I2C, brightness: float, address: int | None = None
) -> Adafruit_RGBMatrixQT:
    """Return a configured IS31FL3741 driver on *i2c*.

    Retries construction for up to :data:`_MATRIX_STARTUP_TIMEOUT_S` seconds
    (useful if the I2C bus is still settling at boot), sleeping ~1s between
    attempts.

    *address* is the configured I2C address override (``MatrixPixelsConfig.address``).
    ``None`` means no override -- the ``address=`` keyword is omitted entirely
    so the driver's own default (``0x30``) applies, rather than passing
    ``address=None``.

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
            if address is None:
                matrix = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
            else:
                matrix = Adafruit_RGBMatrixQT(
                    i2c, address=address, allocate=adafruit_is31fl3741.MUST_BUFFER
                )
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


class CircuitPythonParts(DeviceParts):
    """Builds parts on *board_module*'s pins; *i2c*, if given, is the I2C bus handed out.

    Single-use: every pin is claimed without deiniting, so one adapter serves
    one boot.
    """

    def __init__(self, board_module: object = board, i2c: busio.I2C | None = None) -> None:
        self._board = board_module
        self._i2c = i2c

    def _pin(self, pin: PinRef) -> microcontroller.Pin:
        return _resolve_pin(self._board, pin.field, pin.name)

    def high_current_rail(self, pin: PinRef, level: bool) -> None:
        digitalio.DigitalInOut(self._pin(pin)).switch_to_output(value=level)

    def i2c_bus(self, scl: PinRef | None, sda: PinRef | None) -> busio.I2C | None:
        """Return the injected bus if one is held, else a new bus (``None`` with no pull-up).

        The board default ``SCL``/``SDA`` serve when no pins are declared; a
        board without those aliases raises ``AttributeError``, the nudge to
        declare an ``i2c`` section.
        """
        if self._i2c is not None:
            return self._i2c
        if scl is None or sda is None:
            scl_pin, sda_pin = self._board.SCL, self._board.SDA
        else:
            scl_pin, sda_pin = self._pin(scl), self._pin(sda)
        try:
            return busio.I2C(scl_pin, sda_pin)
        except RuntimeError:  # busio.I2C needs an attached device's pull-up to construct
            return None

    def spi_bus(self, sck: PinRef | None, mosi: PinRef | None, miso: PinRef | None) -> busio.SPI:
        if sck is None or mosi is None or miso is None:
            return self._board.SPI()
        return busio.SPI(self._pin(sck), MOSI=self._pin(mosi), MISO=self._pin(miso))

    def matrix_pixels(self, pixels: MatrixPixelsConfig, i2c: busio.I2C) -> IS31FL3741EffectOutput:
        matrix = _setup_matrix_is31fl3741(i2c, pixels.brightness, pixels.address)
        return IS31FL3741EffectOutput(matrix, cols=pixels.cols, scope_rows=pixels.scope_rows)

    def neopixel_strip(self, strip: NeoPixelStripConfig, pin: PinRef) -> NeoPixelEffectOutput:
        import neopixel

        driver = neopixel.NeoPixel(
            self._pin(pin),
            strip.count,
            pixel_order=strip.order,
            brightness=strip.brightness,
            auto_write=False,
        )
        return NeoPixelEffectOutput(driver, strip.scope_pixels)

    def button_reader(self, pin: PinRef) -> Callable[[], bool]:
        button = digitalio.DigitalInOut(self._pin(pin))
        button.switch_to_input(pull=digitalio.Pull.UP)
        return lambda: button.value
