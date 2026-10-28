"""CircuitPythonParts — the Device assembly's ``DeviceParts`` adapter on a CircuitPython board.

Deploy-watch only: imports board, busio, digitalio and microcontroller. Every
per-part driver library is imported inside the part that builds it, so a config
that doesn't need a part never requires its library to be installed.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TYPE_CHECKING, Final
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

    from hardware.circuitpython.audio_output import AudioEffectOutput
    from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
    from hardware.circuitpython.rfm69_radio_transport import Rfm69RadioTransport
    from hardware.circuitpython.sdcard_storage import SdCardStorage

import time

import board
import busio
import digitalio
import microcontroller

from engine.audio import AudioRegistry
from hardware.circuitpython.infrared_io import PulseInReader, PulseOutWriter
from hardware.circuitpython.is31fl3741_output import IS31FL3741EffectOutput
from hardware.circuitpython.neopixel_output import NeoPixelEffectOutput
from hardware.shared.device_config import (
    AudioConfig,
    I2CDeviceConfig,
    MatrixPixelsConfig,
    NeoPixelStripConfig,
    RadioConfig,
    SDCardConfig,
)
from hardware.shared.device_parts import DeviceParts, PinRef
from hardware.shared.ir_transport import PulseWriter
from hardware.shared.profiler_report import board_id

__all__ = ["CircuitPythonParts", "SdCardMountError"]


class SdCardMountError(RuntimeError):
    """Raised when a declared ``sdcard`` section is present but the card fails to mount.

    Distinguishes a wiring/card fault (no card fitted, no FAT filesystem) from
    other build failures so callers can react to it specifically -- e.g.
    ``examples/sd_sync.py`` reports it and idles rather than crashing into the
    REPL. A ``RuntimeError`` subclass so existing broad ``except RuntimeError``
    handlers still catch it.
    """


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


def _construct_with_optional_address(
    ctor: Callable[..., object], i2c: busio.I2C, address: int | None
) -> object:
    """Return ``ctor(i2c[, address=address])``.

    ``None`` omits the keyword so the driver's own default address applies,
    rather than passing ``address=None``.
    """
    if address is None:
        return ctor(i2c)
    return ctor(i2c, address=address)


def _setup_accelerometer(i2c: busio.I2C, address: int | None = None) -> object:
    """Return a LIS3DH on *i2c*."""
    import adafruit_lis3dh

    return _construct_with_optional_address(adafruit_lis3dh.LIS3DH_I2C, i2c, address)


_MAGNETOMETER_DATA_RATE_HZ: Final = 100

# A dead or mis-wired MMC5603 that still ACKs its I2C address -- parasitically,
# through the shared bus pull-ups -- leaves its output registers reading raw 0 on
# every axis. The adafruit driver maps that raw 0 to a fixed negative full-scale
# value on all three axes at once, a reading no real field can produce (Earth's
# field is always present), so it is a reliable "chip present on the bus but not actually
# converting" sentinel. We must probe for it explicitly because the vendor chip-ID
# guard accepts a 0x00 product ID, so ``MMC5603(i2c)`` construction itself never
# raises in this state. Compared with a tolerance, not ``==``: on-device
# CircuitPython computes the reading in single-precision float, which the
# double-precision module constant below would never equal exactly.
_MAGNETOMETER_DEAD_AXIS_UT: Final = (0 - (1 << 19)) * 0.00625
_MAGNETOMETER_DEAD_TOLERANCE_UT: Final = 0.1
# Up to ~100 ms (several conversion periods at _MAGNETOMETER_DATA_RATE_HZ) before
# giving up: a healthy chip clears the raw-0 state within the first sample; a dead
# one never does, so the margin costs nothing on working hardware.
_MAGNETOMETER_PROBE_ATTEMPTS: Final = 20
_MAGNETOMETER_PROBE_INTERVAL_S: Final = 0.005


def _setup_magnetometer(i2c: busio.I2C, address: int | None = None) -> object:
    """Return an MMC5603 on *i2c*, free-running in continuous mode.

    The MMC5603 boots in one-shot mode, where each ``.magnetic`` read
    busy-waits ~5-10ms for a fresh conversion -- long enough to stall the
    shared input poll every frame. Setting a fixed ``data_rate`` and then
    ``continuous_mode``, in the vendor driver's documented order, makes
    ``.magnetic`` read the latest background sample without blocking.

    Raises:
        RuntimeError: If the chip reads the all-zero sentinel on every axis
            for the whole probe window -- present on the bus but not
            converting (typically a power/ground wiring fault).
    """
    import adafruit_mmc56x3

    chip = _construct_with_optional_address(adafruit_mmc56x3.MMC5603, i2c, address)
    chip.data_rate = _MAGNETOMETER_DATA_RATE_HZ
    chip.continuous_mode = True

    for _ in range(_MAGNETOMETER_PROBE_ATTEMPTS):
        if not all(
            abs(axis - _MAGNETOMETER_DEAD_AXIS_UT) < _MAGNETOMETER_DEAD_TOLERANCE_UT
            for axis in chip.magnetic
        ):
            return chip
        time.sleep(_MAGNETOMETER_PROBE_INTERVAL_S)

    raise RuntimeError(
        "MMC5603 magnetometer ACKs the I2C bus but reads all-zero on every "
        + "axis -- check its power and ground wiring"
    )


def _setup_drv2605(i2c: busio.I2C, address: int | None = None) -> object:
    """Return a DRV2605 haptic driver on *i2c*."""
    import adafruit_drv2605

    return _construct_with_optional_address(adafruit_drv2605.DRV2605, i2c, address)


def _make_writer(pin: microcontroller.Pin) -> tuple[PulseWriter, str]:
    """Return the IR writer the silicon supports for *pin*, and its kind.

    An importable ``rp2pio`` (RP2040/RP2350 only) means the carrier can be
    clocked out by PIO without blocking; any other board falls back to the
    blocking ``pulseio`` writer. PIO support is a property of the silicon, so
    there is no config knob.

    The kind (``"pio"``/``"pulseio"``) is returned alongside the writer rather
    than re-derived for the ``ir`` boot line, which could then diverge from
    what was actually built.
    """
    try:
        import rp2pio  # noqa: F401  # present only on RP2040/RP2350
    except ImportError:
        import pulseio

        pulseout = pulseio.PulseOut(pin, frequency=38000, duty_cycle=0x8000)
        return PulseOutWriter(pulseout), "pulseio"

    from hardware.circuitpython.pio_pulse_writer import (
        PioPulseWriter,
        make_state_machine,
    )

    return PioPulseWriter(make_state_machine(pin)), "pio"


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

    def board_name(self) -> str:
        return board_id()

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

    def accelerometer(self, accelerometer: I2CDeviceConfig, i2c: busio.I2C) -> object:
        return _setup_accelerometer(i2c, accelerometer.address)

    def magnetometer(self, magnetometer: I2CDeviceConfig, i2c: busio.I2C) -> object:
        return _setup_magnetometer(i2c, magnetometer.address)

    def haptic_output(self, haptics: I2CDeviceConfig, i2c: busio.I2C) -> Drv2605EffectOutput:
        driver = _setup_drv2605(i2c, haptics.address)
        # Imported after _setup_drv2605: this module imports adafruit_drv2605 at load time.
        from hardware.circuitpython.drv2605_output import Drv2605EffectOutput

        return Drv2605EffectOutput(driver)

    def audio_output(
        self,
        audio: AudioConfig,
        registry: AudioRegistry,
        bit_clock: PinRef,
        word_select: PinRef,
        data: PinRef,
    ) -> AudioEffectOutput:
        # Its module imports the audio stack (audiobusio/audiocore/audiomixer) at load time.
        from hardware.circuitpython.audio_output import AudioEffectOutput

        return AudioEffectOutput(
            registry,
            max_volume=audio.max_volume,
            num_voices=audio.voices,
            i2s_bit_clock=self._pin(bit_clock),
            i2s_word_select=self._pin(word_select),
            i2s_data=self._pin(data),
        )

    def ir_reader(self, pin: PinRef) -> PulseInReader:
        import pulseio

        return PulseInReader(pulseio.PulseIn(self._pin(pin), maxlen=256, idle_state=True))

    def ir_writer(self, emitter: str, pin: PinRef) -> tuple[PulseWriter, str]:
        return _make_writer(self._pin(pin))

    def radio_transport(
        self, radio: RadioConfig, spi: busio.SPI, cs: PinRef, reset: PinRef
    ) -> Rfm69RadioTransport:
        # The only importer of adafruit_rfm69, which it imports at load time.
        from hardware.circuitpython.rfm69_radio_transport import Rfm69RadioTransport

        return Rfm69RadioTransport(
            spi,
            digitalio.DigitalInOut(self._pin(cs)),
            digitalio.DigitalInOut(self._pin(reset)),
            radio.frequency,
            radio.node,
        )

    def storage(self, sdcard: SDCardConfig, spi: busio.SPI, cs: PinRef) -> SdCardStorage:
        """Return the card mounted at ``sdcard.mount``.

        Raises:
            SdCardMountError: When the card is absent or unmountable.
        """
        # The only importer of sdcardio and storage, which it imports at load time.
        from hardware.circuitpython.sdcard_storage import SdCardStorage

        try:
            return SdCardStorage(spi, self._pin(cs), sdcard.mount)
        except OSError as e:
            raise SdCardMountError(
                f"sdcard section is declared but the card at cs={cs.name} "
                + f"mount={sdcard.mount} failed to mount: {e}"
            ) from e
