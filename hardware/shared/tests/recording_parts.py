"""A ``DeviceParts`` that records every part the Device assembly asks for.

Each request lands in ``requests`` as ``(part, args)``, with ``args`` exactly as
the assembly passed them. ``fail_on`` makes one part raise; ``no_i2c`` makes the
I2C part report that no bus could be built.
"""

from __future__ import annotations

from array import array
from collections.abc import Callable

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
from hardware.shared.device_parts import DeviceParts, PinRef
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_transport import PulseReader, PulseWriter
from hardware.shared.radio_transport import RadioTransport


class PartError(Exception):
    """What a part told to fail raises."""


class Bus:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    def __repr__(self) -> str:
        return f"Bus({self.kind!r})"


class Output(EffectOutput):
    def __init__(self, part: str) -> None:
        super().__init__()
        self.part = part


class Reader(PulseReader):
    def __init__(self, pin: PinRef) -> None:
        self.pin = pin

    def read_pulse(self) -> int | None:
        return None


class Writer(PulseWriter):
    def __init__(self, emitter: str) -> None:
        self.emitter = emitter
        self.written: list[list[int]] = []

    def write_pulses(self, durations: array | list[int]) -> None:
        self.written.append(list(durations))

    def is_busy(self) -> bool:
        return False


class Transport(RadioTransport):
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def send(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def receive(self) -> tuple[int, bytes] | None:
        return None


class RecordingParts(DeviceParts):
    def __init__(
        self, fail_on: str | None = None, no_i2c: bool = False, writer_kind: str = "fake"
    ) -> None:
        self.requests: list[tuple[str, tuple]] = []
        self.pin_levels: dict[str, bool] = {}
        """Raw level each button pin reads, by pin name; ``True`` (released) unless set."""
        self.acceleration: tuple[float, float, float] = (0.0, 0.0, 0.0)
        """What the accelerometer reads."""
        self.writers: dict[str, Writer] = {}
        """Each emitter's writer, by emitter key."""
        self.transports: list[Transport] = []
        self._fail_on = fail_on
        self._no_i2c = no_i2c
        self._writer_kind = writer_kind

    def parts(self) -> list[str]:
        """The parts requested, in order."""
        return [part for part, _args in self.requests]

    def args_of(self, part: str) -> list[tuple]:
        """The arguments of every request for *part*, in order."""
        return [args for name, args in self.requests if name == part]

    def _record(self, part: str, *args: object) -> None:
        self.requests.append((part, args))
        if part == self._fail_on:
            raise PartError(part)

    def board_name(self) -> str:
        self._record("board_name")
        return "test-board"

    def high_current_rail(self, pin: PinRef, level: bool) -> None:
        self._record("high_current_rail", pin, level)

    def i2c_bus(self, scl: PinRef | None, sda: PinRef | None) -> object | None:
        self._record("i2c_bus", scl, sda)
        return None if self._no_i2c else Bus("i2c")

    def spi_bus(self, sck: PinRef | None, mosi: PinRef | None, miso: PinRef | None) -> object:
        self._record("spi_bus", sck, mosi, miso)
        return Bus("spi")

    def matrix_pixels(self, pixels: MatrixPixelsConfig, i2c: object) -> EffectOutput:
        self._record("matrix_pixels", pixels, i2c)
        return Output("matrix_pixels")

    def neopixel_strip(self, strip: NeoPixelStripConfig, pin: PinRef) -> EffectOutput:
        self._record("neopixel_strip", strip, pin)
        return Output("neopixel_strip")

    def button_reader(self, pin: PinRef) -> Callable[[], bool]:
        self._record("button_reader", pin)
        return lambda: self.pin_levels.get(pin.name, True)

    def accelerometer(
        self, accelerometer: I2CDeviceConfig, i2c: object
    ) -> Callable[[], tuple[float, float, float]]:
        self._record("accelerometer", accelerometer, i2c)
        return lambda: self.acceleration

    def magnetometer(self, magnetometer: I2CDeviceConfig, i2c: object) -> object:
        self._record("magnetometer", magnetometer, i2c)
        return object()

    def audio_output(
        self,
        audio: AudioConfig,
        registry: AudioRegistry,
        bit_clock: PinRef,
        word_select: PinRef,
        data: PinRef,
    ) -> EffectOutput:
        self._record("audio_output", audio, registry, bit_clock, word_select, data)
        return Output("audio_output")

    def haptic_output(self, haptics: I2CDeviceConfig, i2c: object) -> EffectOutput:
        self._record("haptic_output", haptics, i2c)
        return Output("haptic_output")

    def ir_reader(self, pin: PinRef) -> PulseReader:
        self._record("ir_reader", pin)
        return Reader(pin)

    def ir_writer(self, emitter: str, pin: PinRef) -> tuple[PulseWriter, str]:
        self._record("ir_writer", emitter, pin)
        self.writers[emitter] = Writer(emitter)
        return self.writers[emitter], self._writer_kind

    def radio_transport(
        self, radio: RadioConfig, spi: object, cs: PinRef, reset: PinRef
    ) -> RadioTransport:
        self._record("radio_transport", radio, spi, cs, reset)
        self.transports.append(Transport())
        return self.transports[-1]

    def storage(self, sdcard: SDCardConfig, spi: object, cs: PinRef) -> DeviceStorage:
        self._record("storage", sdcard, spi, cs)
        return DeviceStorage(sdcard.mount)
