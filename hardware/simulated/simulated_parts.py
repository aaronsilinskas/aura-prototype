"""SimulatedParts — the Simulated device's ``DeviceParts`` adapter.

Builds each part the Device assembly asks for out of simulated stand-ins, and
decides which of them outlive a reboot. The card and the sensors stand for the
physical world a reset leaves alone, so each is built the first time it is
asked for and handed back on every later boot; pixels, audio, the IR readers
and the radio chip are fresh each boot, as a reset clears them. The adapter
never reads ``enabled`` or ``declared``: whatever the assembly asks for is
what the config builds. The card is no stand-in: it is the real
``DeviceStorage`` over the card directory the device was handed.

Pin names and buses are ignored: a bus is a stand-in token, the high-current
rail drives nothing, and there is no matrix.
"""

from __future__ import annotations

import math
import wave
from array import array
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from effects.effect import Effect, PixelBuffer
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.input import AccelerationData
from engine.state import EffectReceipt, Scope, ScopeValue
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
from hardware.shared.voice_pool import VoicePool, VoiceSink, clip_stops_receipt

if TYPE_CHECKING:
    from hardware.simulated.device import SimulatedHardware

__all__ = [
    "DEFAULT_SWAY_STRENGTH",
    "RecordingPixels",
    "SimulatedAccelerometer",
    "SimulatedAudio",
    "SimulatedMagnetometer",
    "SimulatedParts",
    "SimulatedPulseReader",
    "SimulatedRadioTransport",
    "wav_length",
]

_AT_REST = (0.0, 0.0, AccelerationData.GRAVITY)
DEFAULT_SWAY_STRENGTH = 4.0
"""``move``'s sway strength in m/s² unless given one: well above any sensible motion threshold."""
_SWAY_HZ = 2.0
"""``move``'s sway frequency on x: a hand's pace."""

_WRITER_KIND = "simulated"


def wav_length(path: str) -> float:
    """Seconds of audio in the WAV at *path*, read from its header."""
    with wave.open(path, "rb") as clip:
        return clip.getnframes() / clip.getframerate()


_STAND_IN_BUS = object()
"""What a bus part hands out: a token the bus-using parts accept and ignore."""


class SimulatedPulseReader(PulseReader):
    """One IR receiver's pulse buffer: pulses queue up and are read oldest first."""

    def __init__(self) -> None:
        self._pulses: deque[int] = deque()

    def capture(self, pulses: array | list[int]) -> None:
        self._pulses.extend(pulses)

    def read_pulse(self) -> int | None:
        return self._pulses.popleft() if self._pulses else None


class _SimulatedPulseWriter(PulseWriter):
    """One emitter: lights the device's own readers, and records the payload it carried.

    Blocking, like ``pulseio.PulseOut``: a write has finished by the time it
    returns.
    """

    def __init__(self, device: SimulatedHardware, emitter: str) -> None:
        self._device = device
        self._emitter = emitter

    def write_pulses(self, durations: array | list[int]) -> None:
        self._device.on_ir_written(self._emitter, durations)

    def is_busy(self) -> bool:
        return False


class SimulatedRadioTransport(RadioTransport):
    """The radio chip: a send goes to the device, and landed packets wait to be read."""

    def __init__(self, device: SimulatedHardware) -> None:
        self._device = device
        self.waiting: deque[tuple[int, bytes]] = deque()

    def send(self, data: bytes) -> None:
        self._device.on_radio_sent(bytes(data))

    def receive(self) -> tuple[int, bytes] | None:
        return self.waiting.popleft() if self.waiting else None


class RecordingPixels(EffectOutput):
    """One NeoPixel strip's scope segments; keeps each segment's latest frame."""

    def __init__(self, segments: dict[str, range]) -> None:
        super().__init__()
        self.min_resolution = max(len(seg) for seg in segments.values())
        self.scopes = [ScopeValue(key) for key in segments]
        self.frames = {key: [0] * len(seg) for key, seg in segments.items()}

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(len(self.frames[scope_key]))

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        self.frames[scope_key] = list(buffer)

    def clear_pixels(self, scope_key: str) -> None:
        self.frames[scope_key] = [0] * len(self.frames[scope_key])


class SimulatedAudio(EffectOutput, VoiceSink):
    """Plays clips on a real ``VoicePool``; a clip "plays" for its WAV's length.

    Claims through the same ``clip_stops_receipt`` rule as ``AudioEffectOutput``,
    so a ``stops_effect`` clip ends its effect when the clip runs out, exactly as
    on a board.
    """

    def __init__(self, device: SimulatedHardware, registry: AudioRegistry, voices: int) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._device = device
        self._registry = registry
        self._pool = VoicePool(voices)
        self._voices: list[tuple[str, float] | None] = [None] * voices
        """Each voice's clip path and when it ends (``inf`` for a loop), or ``None`` while idle."""

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        if effect.audio is None:
            return
        config = effect.audio.clips.get(event.verb)
        if config is None:
            return
        stops_receipt = clip_stops_receipt(effect, config)
        path = self._registry.path(config.name)
        if self._pool.claim(self, path, config.loop, stops_receipt, receipt) != -1:
            self._device.on_clip_played(config.name)

    def is_clip_playing(self, clip: str) -> bool:
        path = self._registry.path(clip)
        return any(
            voice is not None and voice[0] == path and self.is_playing(slot)
            for slot, voice in enumerate(self._voices)
        )

    def flush(self) -> None:
        self._pool.sweep(self)

    def open_source(self, path: str) -> object | None:
        return (path, wav_length(path))

    def play(self, slot: int, source: object, loop: bool) -> None:
        assert isinstance(source, tuple)  # the (path, length) open_source returned
        path, length = source
        self._voices[slot] = (path, math.inf if loop else self._device.now() + length)

    def stop(self, slot: int) -> None:
        self._voices[slot] = None

    def set_loudness(self, slot: int, loudness: float) -> None:
        pass

    def is_playing(self, slot: int) -> bool:
        voice = self._voices[slot]
        return voice is not None and self._device.now() < voice[1]


class _RecordingHaptic(EffectOutput):
    def __init__(self, device: SimulatedHardware) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._device = device

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        if effect.haptic is None:
            return
        pattern = effect.haptic.patterns.get(event.verb)
        if pattern is not None:
            self._device.on_buzzed(tuple(pattern.sequence))


class SimulatedAccelerometer:
    """An accelerometer reading a held ``(x, y, z)`` in m/s², plus any sway on x."""

    def __init__(self, now: Callable[[], float]) -> None:
        self._now = now
        self._held = _AT_REST
        self._sway_strength = DEFAULT_SWAY_STRENGTH
        self._sway_from: float | None = None
        """When the sway started, or ``None`` while the device is not moving."""

    @property
    def acceleration(self) -> tuple[float, float, float]:
        x, y, z = self._held
        if self._sway_from is not None:
            phase = 2 * math.pi * _SWAY_HZ * (self._now() - self._sway_from)
            x += self._sway_strength * math.sin(phase)
        return (x, y, z)

    def hold(self, x: float, y: float, z: float) -> None:
        self._held = (x, y, z)

    def sway(self, strength: float) -> None:
        self._sway_strength = strength
        self._sway_from = self._now()

    def rest(self) -> None:
        self._held = _AT_REST
        self._sway_from = None


class SimulatedMagnetometer:
    """A magnetometer reading a held raw field ``(x, y, z)`` in µT; zero until set."""

    def __init__(self) -> None:
        self.magnetic = (0.0, 0.0, 0.0)


class _KeptParts:
    """The parts that outlive a reboot; each ``None`` until first asked for."""

    def __init__(self) -> None:
        self.storage: DeviceStorage | None = None
        self.accelerometer: SimulatedAccelerometer | None = None
        self.magnetometer: SimulatedMagnetometer | None = None


class SimulatedParts(DeviceParts):
    """The parts of one boot of *device*; *previous* is the boot before it, if any.

    The parts built fresh this boot are kept here for the device's scripting
    helpers to reach: ``strips``, ``audio``, ``ir_readers``, ``ir_emitters``
    (in the order wired) and ``radio``; ``scripted_accelerometer`` and
    ``scripted_magnetometer`` are kept across reboots.
    """

    def __init__(self, device: SimulatedHardware, previous: SimulatedParts | None = None) -> None:
        self._device = device
        self._kept = previous._kept if previous is not None else _KeptParts()
        self.strips: list[RecordingPixels] = []
        self.audio: SimulatedAudio | None = None
        self.ir_readers: list[SimulatedPulseReader] = []
        self.ir_emitters: list[str] = []
        self.radio: SimulatedRadioTransport | None = None

    def board_name(self) -> str:
        return "simulated"

    def high_current_rail(self, pin: PinRef, level: bool) -> None:
        pass

    def i2c_bus(self, scl: PinRef | None, sda: PinRef | None) -> object | None:
        return _STAND_IN_BUS

    def spi_bus(self, sck: PinRef | None, mosi: PinRef | None, miso: PinRef | None) -> object:
        return _STAND_IN_BUS

    def matrix_pixels(self, pixels: MatrixPixelsConfig, i2c: object) -> EffectOutput:
        raise ValueError("the Simulated device has no matrix; lay pixels out as strips")

    def neopixel_strip(self, strip: NeoPixelStripConfig, pin: PinRef) -> EffectOutput:
        self.strips.append(RecordingPixels(strip.scope_pixels))
        return self.strips[-1]

    def button_reader(self, pin: PinRef) -> Callable[[], bool]:
        return lambda: self._device.pin_level(pin.name)

    @property
    def scripted_accelerometer(self) -> SimulatedAccelerometer | None:
        """The accelerometer the device scripts; ``None`` until a boot first builds one."""
        return self._kept.accelerometer

    def accelerometer(
        self, accelerometer: I2CDeviceConfig, i2c: object
    ) -> Callable[[], tuple[float, float, float]]:
        if self._kept.accelerometer is None:
            self._kept.accelerometer = SimulatedAccelerometer(self._device.now)
        scripted = self._kept.accelerometer
        return lambda: scripted.acceleration

    @property
    def scripted_magnetometer(self) -> SimulatedMagnetometer | None:
        """The magnetometer the device scripts; ``None`` until a boot first builds one."""
        return self._kept.magnetometer

    def magnetometer(
        self, magnetometer: I2CDeviceConfig, i2c: object
    ) -> Callable[[], tuple[float, float, float]]:
        if self._kept.magnetometer is None:
            self._kept.magnetometer = SimulatedMagnetometer()
        scripted = self._kept.magnetometer
        return lambda: scripted.magnetic

    def audio_output(
        self,
        audio: AudioConfig,
        registry: AudioRegistry,
        bit_clock: PinRef,
        word_select: PinRef,
        data: PinRef,
    ) -> EffectOutput:
        self.audio = SimulatedAudio(self._device, registry, audio.voices)
        return self.audio

    def haptic_output(self, haptics: I2CDeviceConfig, i2c: object) -> EffectOutput:
        return _RecordingHaptic(self._device)

    def ir_reader(self, pin: PinRef) -> PulseReader:
        self.ir_readers.append(SimulatedPulseReader())
        return self.ir_readers[-1]

    def ir_writer(self, emitter: str, pin: PinRef) -> tuple[PulseWriter, str]:
        self.ir_emitters.append(emitter)
        return _SimulatedPulseWriter(self._device, emitter), _WRITER_KIND

    def radio_transport(
        self, radio: RadioConfig, spi: object, cs: PinRef, reset: PinRef
    ) -> RadioTransport:
        self.radio = SimulatedRadioTransport(self._device)
        return self.radio

    def storage(self, sdcard: SDCardConfig, spi: object, cs: PinRef) -> DeviceStorage:
        if self._kept.storage is None:
            if self._device.card is None:
                raise ValueError("an enabled sdcard section needs a card directory")
            self._kept.storage = DeviceStorage(self._device.card)
        return self._kept.storage
