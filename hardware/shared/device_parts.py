"""DeviceParts — the port the Device assembly reaches leaf hardware through.

One constructor per part. Parts take config sections and :class:`PinRef` values,
never pin objects, so the assembly stays board-free and a pin error can still
name the config field it came from. Every gating and bus-requirement decision
belongs to the assembly (``hardware.shared.device_assembly``); an adapter only
builds what it is asked for. One adapter per platform.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
except ImportError:
    pass

from engine.effects.output import EffectOutput
from hardware.shared.device_config import (
    AudioConfig,
    I2CDeviceConfig,
    MatrixPixelsConfig,
    NeoPixelStripConfig,
    PinRef,
    RadioConfig,
    SDCardConfig,
)
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transport import PulseReader, PulseWriter
from hardware.shared.radio_transport import RadioTransport

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Any

    # A platform's bus object: the Device assembly only passes it along, and
    # each adapter narrows it to the bus type its parts take.
    Bus = Any

__all__ = ["DeviceParts"]


class DeviceParts:
    """Builds one part at a time for the Device assembly.

    A bus is a :data:`Bus`: whatever the platform's bus-using parts accept;
    the assembly only passes it along.
    """

    def board_name(self) -> str:
        raise NotImplementedError

    def high_current_rail(self, pin: PinRef, level: bool) -> None:
        """Drive the rail's *pin* to *level*."""
        raise NotImplementedError

    def i2c_bus(self, scl: PinRef | None, sda: PinRef | None) -> Bus | None:
        """Return an I2C bus on *scl*/*sda*, or the board default when both are ``None``.

        ``None`` means no bus could be built: nothing on the bus to pull it
        up, or the board has no default I2C bus.
        """
        raise NotImplementedError

    def spi_bus(self, sck: PinRef | None, mosi: PinRef | None, miso: PinRef | None) -> Bus | None:
        """Return an SPI bus on the given pins, or the board default when all are ``None``.

        ``None`` means the board has no default SPI bus.
        """
        raise NotImplementedError

    def matrix_pixels(self, pixels: MatrixPixelsConfig, i2c: Bus) -> EffectOutput:
        raise NotImplementedError

    def neopixel_strip(self, strip: NeoPixelStripConfig, pin: PinRef) -> EffectOutput:
        """Return the output for one physical strip, segmented by ``strip.scope_pixels``."""
        raise NotImplementedError

    def button_reader(self, pin: PinRef) -> Callable[[], bool]:
        """Return a raw-level read of a pulled-up button pin: ``True`` while not pressed."""
        raise NotImplementedError

    def accelerometer(
        self, accelerometer: I2CDeviceConfig, i2c: Bus
    ) -> Callable[[], tuple[float, float, float]]:
        """Return a raw read of the accelerometer: ``(x, y, z)`` in m/s², which may raise."""
        raise NotImplementedError

    def magnetometer(
        self, magnetometer: I2CDeviceConfig, i2c: Bus
    ) -> Callable[[], tuple[float, float, float]]:
        """Return a raw read of the magnetometer: ``(x, y, z)`` in µT, which may raise."""
        raise NotImplementedError

    def audio_output(
        self,
        audio: AudioConfig,
        bit_clock: PinRef,
        word_select: PinRef,
        data: PinRef,
    ) -> EffectOutput:
        """Return the audio output; it plays the path on each event's resolved clip."""
        raise NotImplementedError

    def haptic_output(self, haptics: I2CDeviceConfig, i2c: Bus) -> EffectOutput:
        raise NotImplementedError

    def ir_reader(self, pin: PinRef) -> PulseReader:
        raise NotImplementedError

    def ir_writer(self, emitter: str, pin: PinRef) -> tuple[PulseWriter, str]:
        """Return *emitter*'s pulse writer and the writer kind it is (e.g. ``"pio"``)."""
        raise NotImplementedError

    def radio_transport(
        self, radio: RadioConfig, spi: Bus, cs: PinRef, reset: PinRef
    ) -> RadioTransport:
        raise NotImplementedError

    def storage(self, sdcard: SDCardConfig, spi: Bus, cs: PinRef) -> DeviceStorage:
        raise NotImplementedError
