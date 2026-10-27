"""The Simulated device: scripted pins in, recorded outputs out.

Builds a real ``DeviceHardware`` around a real ``DebouncedButtons`` and a real
``VoicePool``, so input debouncing and clip-driven effect endings behave as on
a board. It obeys the hardware import contract: it knows nothing about scenes,
the engine loop, or time beyond the ``now`` it is handed.

Its shape comes from a ``DeviceConfig``: one button per declared pin, labelled
``A`` onward as on a board; one recording pixel output per NeoPixel strip; the
declared voice count; a haptic output when ``haptics`` is declared; an
accelerometer when ``accelerometer`` is declared; the real
``InfraredTransceiver`` over one simulated reader per ``ir.rx`` pin and one
simulated writer per wired emitter. Wiring (pins, buses, addresses) is
otherwise ignored; an enabled ``sdcard`` section is an in-memory card. Matrix
pixels, the magnetometer, and the radio are not simulated.

IR pulses are ideal: a write lands at exactly the codec's durations, with no
noise, jitter, or airtime. What an emitter writes reaches the device's own
readers at once, as a lit emitter does on a board, so the real transmit gate is
what keeps a device from hearing itself. Each write is also handed, with its
emitter, to the optional ``ir_sink``; ``land_ir`` lands pulses from elsewhere on
chosen receivers. Which other devices hear a write is the harness's business:
this device knows of no other.
"""

from __future__ import annotations

import copy
import math
import wave
from array import array
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from effects.effect import Effect, PixelBuffer
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.input import AccelerationData, ButtonData
from engine.network import IR_EMITTERS
from engine.state import EffectReceipt, Scope, ScopeValue
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import DeviceConfig, MatrixPixelsConfig
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_codecs.aura import AuraInfraredDecoder, AuraInfraredEncoder
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import (
    InfraredMultiReceiver,
    InfraredReceiver,
    InfraredSingleReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.voice_pool import VoicePool, VoiceSink, clip_stops_receipt
from hardware.simulated.storage import FakeDeviceStorage

__all__ = ["DEFAULT_SWAY_STRENGTH", "Buzzed", "IrSent", "Played", "SimulatedHardware", "Strip"]

_DEBOUNCE_INTERVAL = 0.05
_PIN_SETTLE = 2 * _DEBOUNCE_INTERVAL
"""How long a scripted pin level holds before the next change may start.

Long enough for the debouncer to commit it, so every scripted press and
release registers and tests never need to know the debounce interval.
"""

_AT_REST = (0.0, 0.0, AccelerationData.GRAVITY)
DEFAULT_SWAY_STRENGTH = 4.0
"""``move``'s sway strength in m/s² unless given one: well above any sensible motion threshold."""
_SWAY_HZ = 2.0
"""``move``'s sway frequency on x: a hand's pace."""


@dataclass(frozen=True)
class IrSent:
    at: float
    emitter: str
    payload: bytes


@dataclass(frozen=True)
class Played:
    at: float
    clip: str


@dataclass(frozen=True)
class Buzzed:
    at: float
    pattern: tuple[int, ...]


def _channels(pixel: int) -> tuple[int, int, int]:
    return (pixel >> 16) & 0xFF, (pixel >> 8) & 0xFF, pixel & 0xFF


def _is_shade(pixel: int, color: int) -> bool:
    """Whether lit *pixel* is *color* scaled toward black, give or take a step of rounding.

    A channel *color* leaves dark must stay dark, so rounding never passes off
    another hue as a shade.
    """
    shown, wanted = _channels(pixel), _channels(color)
    peak = max(range(3), key=lambda c: wanted[c])
    if shown[peak] == 0 or shown[peak] > wanted[peak]:
        return False
    scale = shown[peak] / wanted[peak]
    return all(
        s == 0 if w == 0 else abs(s - w * scale) <= 1 for s, w in zip(shown, wanted, strict=True)
    )


class Strip:
    """The latest frame a scope showed, with semantic reads over it."""

    def __init__(self, pixels: list[int]) -> None:
        self.pixels = pixels

    @property
    def size(self) -> int:
        return len(self.pixels)

    @property
    def lit(self) -> int:
        return sum(1 for p in self.pixels if p != 0)

    @property
    def dark(self) -> bool:
        return self.lit == 0

    def all_lit(self, color: int) -> bool:
        return all(p == color for p in self.pixels)

    def shades_of(self, color: int) -> bool:
        """Whether every lit pixel is a shade of *color*; dark pixels are allowed."""
        return all(_is_shade(p, color) for p in self.pixels if p != 0)

    def __repr__(self) -> str:
        return "Strip(" + " ".join(f"{p:06X}" for p in self.pixels) + ")"


class _SimulatedPulseReader(PulseReader):
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

    def __init__(self, sim_hw: SimulatedHardware, emitter: str) -> None:
        self._sim_hw = sim_hw
        self._emitter = emitter

    def write_pulses(self, durations: array | list[int]) -> None:
        self._sim_hw._emit(self._emitter, durations)

    def is_busy(self) -> bool:
        return False


def _wav_length(path: str) -> float:
    """Seconds of audio in the WAV at *path*, read from its header."""
    with wave.open(path, "rb") as clip:
        return clip.getnframes() / clip.getframerate()


class _RecordingPixels(EffectOutput):
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


class _SimulatedAudio(EffectOutput, VoiceSink):
    """Plays clips on a real ``VoicePool``; a clip "plays" for its WAV's length.

    Claims through the same ``clip_stops_receipt`` rule as ``AudioEffectOutput``,
    so a ``stops_effect`` clip ends its effect when the clip runs out, exactly as
    on a board.
    """

    def __init__(self, sim_hw: SimulatedHardware, registry: AudioRegistry, voices: int) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._sim_hw = sim_hw
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
            self._sim_hw.played.append(Played(self._sim_hw.now(), config.name))

    def is_clip_playing(self, clip: str) -> bool:
        path = self._registry.path(clip)
        return any(
            voice is not None and voice[0] == path and self.is_playing(slot)
            for slot, voice in enumerate(self._voices)
        )

    def flush(self) -> None:
        self._pool.sweep(self)

    def open_source(self, path: str) -> object | None:
        return (path, _wav_length(path))

    def play(self, slot: int, source: object, loop: bool) -> None:
        assert isinstance(source, tuple)  # the (path, length) open_source returned
        path, length = source
        self._voices[slot] = (path, math.inf if loop else self._sim_hw.now() + length)

    def stop(self, slot: int) -> None:
        self._voices[slot] = None

    def set_loudness(self, slot: int, loudness: float) -> None:
        pass

    def is_playing(self, slot: int) -> bool:
        voice = self._voices[slot]
        return voice is not None and self._sim_hw.now() < voice[1]


class _RecordingHaptic(EffectOutput):
    def __init__(self, sim_hw: SimulatedHardware) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._sim_hw = sim_hw

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        if effect.haptic is None:
            return
        pattern = effect.haptic.patterns.get(event.verb)
        if pattern is not None:
            self._sim_hw.buzzed.append(Buzzed(self._sim_hw.now(), tuple(pattern.sequence)))


class _SimulatedAccelerometer:
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


class _CountingButtons(DebouncedButtons):
    """The real debouncer, also counting each button's registered releases into *releases*."""

    def __init__(
        self,
        buttons: list[tuple[str, Callable[[], bool]]],
        interval: float,
        releases: dict[str, int],
    ) -> None:
        super().__init__(buttons, interval=interval)
        self.releases = releases

    def update(self, elapsed: float, out: ButtonData) -> None:
        super().update(elapsed, out)
        for label in self.releases:
            if out.is_released(label):
                self.releases[label] += 1


def _strip_segments(config: DeviceConfig) -> list[dict[str, range]]:
    """Each enabled NeoPixel strip's scope segments, one dict per strip."""
    strips: list[dict[str, range]] = []
    for entry in config.pixels:
        if isinstance(entry, MatrixPixelsConfig):
            raise ValueError("the Simulated device has no matrix; lay pixels out as strips")
        if not entry.enabled:
            continue
        strips.extend(strip.scope_pixels for strip in entry.strips)
    return strips


class SimulatedHardware:
    """A Simulated device: ``hw`` is the ``DeviceHardware`` a scene boots on.

    *now* reads the simulation clock; every recording is stamped with it, and
    scripted pin changes fall due against it. Call ``settle_pins`` once per
    tick, before the tick reads the buttons. *ir_sink*, when given, is handed
    every emitter write as ``(emitter, pulses)``.

    ``hw.storage`` is an in-memory card when the config declares an enabled
    ``sdcard`` section, else ``None``. ``power_on`` resets the device: ``hw``
    is rebuilt with its outputs dark and silent, while the card, the pins,
    the accelerometer, what the IR receivers have caught, and the recordings
    carry on.
    """

    def __init__(
        self,
        now: Callable[[], float],
        config: DeviceConfig,
        ir_sink: Callable[[str, list[int]], None] | None = None,
    ) -> None:
        self.now = now
        self._config = config
        self._ir_sink = ir_sink
        self.ir_sent: list[IrSent] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        self._labels = [chr(ord("A") + i) for i in range(len(config.buttons))]
        self._pressed = dict.fromkeys(self._labels, False)
        self._pin_changes: dict[str, list[tuple[float, bool]]] = {b: [] for b in self._labels}
        self._pin_free_at = dict.fromkeys(self._labels, 0.0)
        self._releases = dict.fromkeys(self._labels, 0)
        ir_config = config.ir if config.ir is not None and config.ir.enabled else None
        self._ir_readers = (
            [_SimulatedPulseReader() for _ in ir_config.rx] if ir_config is not None else []
        )
        self._wired_emitters = (
            tuple(e for e in IR_EMITTERS if e in ir_config.emitters)
            if ir_config is not None
            else ()
        )
        self._accelerometer = (
            _SimulatedAccelerometer(now)
            if config.accelerometer is not None and config.accelerometer.enabled
            else None
        )
        self._storage = (
            FakeDeviceStorage() if config.sdcard is not None and config.sdcard.enabled else None
        )
        self.power_on()

    def power_on(self) -> None:
        """Build ``hw`` afresh, as a reset does: the debouncer reads the pins as they stand.

        A button held through it stays down without a new press. Strips are
        dark, no clip plays, and the device speaks the Aura wire-frame until
        ``apply_ir_codec``.
        """
        config = self._config
        self._buttons = _CountingButtons(
            [(label, self._pin_reader(label)) for label in self._labels],
            interval=_DEBOUNCE_INTERVAL,
            releases=self._releases,
        )
        self._strips = [_RecordingPixels(segments) for segments in _strip_segments(config)]
        self._audio_registry = AudioRegistry()
        outputs: list[EffectOutput] = [*self._strips]
        self._audio = (
            _SimulatedAudio(self, self._audio_registry, config.audio.voices)
            if config.audio is not None and config.audio.enabled
            else None
        )
        if self._audio is not None:
            outputs.append(self._audio)
        if config.haptics is not None and config.haptics.enabled:
            outputs.append(_RecordingHaptic(self))
        self._ir_receiver: InfraredReceiver | None = None
        self._ir_encoder: InfraredEncoder = AuraInfraredEncoder()
        self._wire_decoder: InfraredDecoder = AuraInfraredDecoder()
        ir = self._build_ir() if self._ir_readers else None
        self.hw = DeviceHardware(
            outputs=outputs,
            buttons=self._buttons,
            accelerometer=self._accelerometer,
            magnetometer=None,
            network_controls=HardwareNetworkControls(ir),
            ir=ir,
            radio=None,
            storage=self._storage,
            audio_registry=self._audio_registry,
        )

    def apply_ir_codec(self, encoder: InfraredEncoder, decoder: InfraredDecoder) -> None:
        """Install the wire-frame codec, as ``run_scene`` does before the first tick.

        Also sets the codec ``receive_ir`` encodes through and ``ir_sent``
        decodes with. Until called, the device speaks the Aura wire-frame, as
        ``device_builder`` defaults to.
        """
        self._ir_encoder = encoder
        self._wire_decoder = copy.deepcopy(decoder)  # the receiver keeps *decoder* itself
        if self.hw.ir is not None:
            self.hw.ir.apply_codec(encoder, decoder)

    def receive_ir(self, payload: bytes) -> None:
        """Land a clean shot carrying *payload* on every IR receiver.

        Encoded through the installed codec; the transceiver's next
        ``update`` decodes it.
        """
        self.land_ir(self._ir_encoder.encode(payload))

    def land_ir(self, pulses: array | list[int], receivers: Sequence[int] | None = None) -> None:
        """Land *pulses* on the IR receivers at indexes *receivers*, or on every one.

        Already encoded: whatever wire-frame they carry, the transceiver's
        next ``update`` decodes them with the installed codec, or fails to.
        """
        readers = (
            self._ir_readers if receivers is None else [self._ir_readers[i] for i in receivers]
        )
        for reader in readers:
            reader.capture(pulses)

    @property
    def ir_emitters(self) -> tuple[str, ...]:
        """The emitters the config wires, in ``IR_EMITTERS`` order."""
        return self._wired_emitters

    @property
    def ir_receiver_count(self) -> int:
        return len(self._ir_readers)

    @property
    def best_receiver(self) -> int | None:
        """Index of the IR receiver the multi-receiver picked for the latest shot.

        ``None`` before any shot, or with fewer than two receivers, where
        there is no pick to make.
        """
        if self._ir_receiver is None:
            return None
        best = self._ir_receiver.last_best_receiver
        return next((i for i, reader in enumerate(self._ir_readers) if reader is best), None)

    def clip_length(self, clip: str) -> float:
        """Seconds *clip* plays for, read from the WAV header it plays from."""
        return _wav_length(self._audio_registry.path(clip))

    def is_playing(self, clip: str) -> bool:
        return self._audio is not None and self._audio.is_clip_playing(clip)

    def releases(self, button: str) -> int:
        """How many releases of *button* the debouncer has registered so far."""
        return self._releases[button]

    def accelerate(self, x: float, y: float, z: float) -> None:
        self._require_accelerometer().hold(x, y, z)

    def move(self, strength: float = DEFAULT_SWAY_STRENGTH) -> None:
        """Sway *strength* m/s² either side of the held reading on x."""
        self._require_accelerometer().sway(strength)

    def hold_still(self) -> None:
        self._require_accelerometer().rest()

    def hold(self, button: str) -> None:
        self._schedule(button, True)

    def release(self, button: str) -> None:
        self._schedule(button, False)

    def settle_pins(self) -> None:
        """Apply every scripted pin change that has fallen due."""
        now = self.now()
        for button, changes in self._pin_changes.items():
            while changes and changes[0][0] <= now:
                self._pressed[button] = changes.pop(0)[1]

    def strip(self, scope: ScopeValue) -> Strip:
        """The latest frame of the one strip segment showing leaf *scope*."""
        (key,) = scope.keys
        frames = [s.frames[key] for s in self._strips if key in s.frames]
        if len(frames) != 1:
            raise KeyError(f"{len(frames)} strips show scope '{key}'; expected exactly one")
        return Strip(frames[0])

    def forget(self) -> None:
        self.ir_sent.clear()
        self.played.clear()
        self.buzzed.clear()

    def _build_ir(self) -> InfraredTransceiver:
        """Assemble the real IR stack the way ``device_builder`` does, on simulated pulses."""
        gate = IrTransmitGate()
        receiver: InfraredReceiver
        if len(self._ir_readers) == 1:
            receiver = InfraredSingleReceiver(self._ir_readers[0], AuraInfraredDecoder(), gate)
        else:
            receiver = InfraredMultiReceiver(list(self._ir_readers), AuraInfraredDecoder, gate)
        self._ir_receiver = receiver
        transmitters = {
            emitter: InfraredTransmitter(
                _SimulatedPulseWriter(self, emitter), self._ir_encoder, gate
            )
            for emitter in self._wired_emitters
        }
        return InfraredTransceiver(transmitters, receiver, gate)

    def _emit(self, emitter: str, pulses: array | list[int]) -> None:
        """Record what *emitter* carried, let the device's own readers see it, and hand it on."""
        self.ir_sent.append(IrSent(self.now(), emitter, self._decode_wire(pulses)))
        self.land_ir(pulses)
        if self._ir_sink is not None:
            self._ir_sink(emitter, list(pulses))

    def _decode_wire(self, pulses: array | list[int]) -> bytes:
        """The payload *pulses* carry, read back through the installed codec."""
        decoder = self._wire_decoder
        decoder.reset()
        for pulse in pulses:
            payload = decoder.decode(pulse)
            if payload is not None:
                return bytes(payload)
        raise ValueError(f"the {decoder.__class__.__name__} cannot read back what was sent")

    def _require_accelerometer(self) -> _SimulatedAccelerometer:
        if self._accelerometer is None:
            raise ValueError("the config declares no accelerometer")
        return self._accelerometer

    def _schedule(self, button: str, pressed: bool) -> None:
        # Queued behind the previous change, so back-to-back calls never land
        # inside the debounce window and get swallowed.
        at = max(self.now(), self._pin_free_at[button])
        self._pin_changes[button].append((at, pressed))
        self._pin_free_at[button] = at + _PIN_SETTLE

    def _pin_reader(self, label: str) -> Callable[[], bool]:
        return lambda: not self._pressed[label]  # pull-up: HIGH means not pressed
