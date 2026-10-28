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

from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from hardware.shared.device_config import (
    AudioConfig,
    I2CDeviceConfig,
    MatrixPixelsConfig,
    NeoPixelStripConfig,
    RadioConfig,
    SDCardConfig,
)
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transport import PulseReader, PulseWriter
from hardware.shared.radio_transport import RadioTransport

__all__ = ["DeviceParts", "PinRef"]


class PinRef:
    """A pin name paired with the config field it came from, e.g. ``GP7`` from ``ir.left``."""

    __slots__ = ("field", "name")

    def __init__(self, name: str, field: str) -> None:
        self.name: str = name
        self.field: str = field

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PinRef) and (self.name, self.field) == (other.name, other.field)

    def __hash__(self) -> int:
        return hash((self.name, self.field))

    def __repr__(self) -> str:
        return f"PinRef({self.name!r}, {self.field!r})"


class DeviceParts:
    """Builds one part at a time for the Device assembly.

    A bus is whatever object the platform's bus-using parts accept; the
    assembly only passes it along.
    """

    def board_name(self) -> str:
        raise NotImplementedError

    def high_current_rail(self, pin: PinRef, level: bool) -> None:
        """Drive the rail's *pin* to *level*."""
        raise NotImplementedError

    def i2c_bus(self, scl: PinRef | None, sda: PinRef | None) -> object | None:
        """Return an I2C bus on *scl*/*sda*, or the board default when both are ``None``.

        ``None`` means no bus could be built (nothing on the bus to pull it up).
        """
        raise NotImplementedError

    def spi_bus(self, sck: PinRef | None, mosi: PinRef | None, miso: PinRef | None) -> object:
        """Return an SPI bus on the given pins, or the board default when all are ``None``."""
        raise NotImplementedError

    def matrix_pixels(self, pixels: MatrixPixelsConfig, i2c: object) -> EffectOutput:
        raise NotImplementedError

    def neopixel_strip(self, strip: NeoPixelStripConfig, pin: PinRef) -> EffectOutput:
        """Return the output for one physical strip, segmented by ``strip.scope_pixels``."""
        raise NotImplementedError

    def button_reader(self, pin: PinRef) -> Callable[[], bool]:
        """Return a raw-level read of a pulled-up button pin: ``True`` while not pressed."""
        raise NotImplementedError

    def accelerometer(self, accelerometer: I2CDeviceConfig, i2c: object) -> object:
        raise NotImplementedError

    def magnetometer(self, magnetometer: I2CDeviceConfig, i2c: object) -> object:
        raise NotImplementedError

    def audio_output(
        self,
        audio: AudioConfig,
        registry: AudioRegistry,
        bit_clock: PinRef,
        word_select: PinRef,
        data: PinRef,
    ) -> EffectOutput:
        """Return the audio output, resolving clip names through *registry*."""
        raise NotImplementedError

    def haptic_output(self, haptics: I2CDeviceConfig, i2c: object) -> EffectOutput:
        raise NotImplementedError

    def ir_reader(self, pin: PinRef) -> PulseReader:
        raise NotImplementedError

    def ir_writer(self, emitter: str, pin: PinRef) -> tuple[PulseWriter, str]:
        """Return *emitter*'s pulse writer and the writer kind it is (e.g. ``"pio"``)."""
        raise NotImplementedError

    def radio_transport(
        self, radio: RadioConfig, spi: object, cs: PinRef, reset: PinRef
    ) -> RadioTransport:
        raise NotImplementedError

    def storage(self, sdcard: SDCardConfig, spi: object, cs: PinRef) -> DeviceStorage:
        raise NotImplementedError
