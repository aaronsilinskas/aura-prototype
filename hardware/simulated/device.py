"""The Simulated device: scripted pins in, recorded outputs out.

Builds a real ``DeviceHardware`` around a real ``DebouncedButtons`` and a real
``VoicePool``, so input debouncing and clip-driven effect endings behave as on
a board. It obeys the hardware import contract: it knows nothing about scenes,
the engine loop, or time beyond the ``now`` it is handed.

Its shape comes from a ``DeviceConfig``: one button per declared pin, labelled
``A`` onward as on a board; one recording pixel output per NeoPixel strip; the
declared voice count; a haptic output when ``haptics`` is declared; an
accelerometer when ``accelerometer`` is declared; a magnetometer when
``magnetometer`` is declared; the real
``InfraredTransceiver`` over one simulated reader per ``ir.rx`` pin and one
simulated writer per wired emitter; the real ``RadioTransceiver`` over a
simulated ``RadioTransport`` when ``radio`` is declared, sending as its
``node``. Wiring (pins, buses, addresses) is otherwise ignored; an enabled
``sdcard`` section is an in-memory card. Matrix pixels are not simulated.

IR pulses are ideal: a write lands at exactly the codec's durations, with no
noise, jitter, or airtime. What an emitter writes reaches the device's own
readers at once, as a lit emitter does on a board, so the real transmit gate is
what keeps a device from hearing itself. Each write is also handed, with its
emitter, to the optional ``ir_sink``; ``land_ir`` lands pulses from elsewhere on
chosen receivers. Which other devices hear a write is the harness's business:
this device knows of no other.

Radio is ideal too: a send is handed, whole, to the optional ``radio_sink``
and never reaches the device's own radio, as the half-duplex chip never hears
itself. ``land_radio`` lands a packet from elsewhere, where it waits, in turn,
to be read.
"""

from __future__ import annotations

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
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.ir_transport import (
    InfraredReceiver,
    InfraredTransmitter,
    IrTransmitGate,
    PulseReader,
    PulseWriter,
)
from hardware.shared.network_controls import HardwareNetworkControls
from hardware.shared.radio_transceiver import RadioTransceiver
from hardware.shared.radio_transport import RadioTransport
from hardware.shared.voice_pool import VoicePool, VoiceSink, clip_stops_receipt
from hardware.simulated.storage import FakeDeviceStorage

__all__ = [
    "DEFAULT_SWAY_STRENGTH",
    "Buzzed",
    "IrSent",
    "Played",
    "RadioSent",
    "SimulatedHardware",
    "Strip",
]

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
class RadioSent:
    at: float
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


class _SimulatedRadioTransport(RadioTransport):
    """The radio chip: a send goes to the device, and landed packets wait to be read."""

    def __init__(self, sim_hw: SimulatedHardware) -> None:
        self._sim_hw = sim_hw
        self.waiting: deque[tuple[int, bytes]] = deque()

    def send(self, data: bytes) -> None:
        self._sim_hw._send_radio(bytes(data))

    def receive(self) -> tuple[int, bytes] | None:
        return self.waiting.popleft() if self.waiting else None


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


class _SimulatedMagnetometer:
    """A magnetometer reading a held raw field ``(x, y, z)`` in µT; zero until set."""

    def __init__(self) -> None:
        self.magnetic = (0.0, 0.0, 0.0)


class _ReadingButtons(DebouncedButtons):
    """The real debouncer, also keeping in *down* whether it last read each button as down."""

    def __init__(
        self,
        buttons: list[tuple[str, Callable[[], bool]]],
        interval: float,
        down: dict[str, bool],
    ) -> None:
        super().__init__(buttons, interval=interval)
        self.down = down

    def update(self, elapsed: float, out: ButtonData) -> None:
        super().update(elapsed, out)
        for label in self.down:
            self.down[label] = out.is_down(label)


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
    every emitter write as ``(emitter, pulses)``, and *radio_sink* every radio
    send's payload.

    ``hw.storage`` is an in-memory card when the config declares an enabled
    ``sdcard`` section, else ``None``. ``power_on`` resets the device: see
    there for what it rebuilds.
    """

    def __init__(
        self,
        now: Callable[[], float],
        config: DeviceConfig,
        ir_sink: Callable[[str, list[int]], None] | None = None,
        radio_sink: Callable[[bytes], None] | None = None,
    ) -> None:
        self.now = now
        self._config = config
        self._ir_sink = ir_sink
        self._radio_sink = radio_sink
        self.ir_sent: list[IrSent] = []
        self.radio_sent: list[RadioSent] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        self._labels = [chr(ord("A") + i) for i in range(len(config.buttons))]
        self._pressed = dict.fromkeys(self._labels, False)
        self._pin_changes: dict[str, list[tuple[float, bool]]] = {b: [] for b in self._labels}
        self._pin_free_at = dict.fromkeys(self._labels, 0.0)
        self._read_down = dict.fromkeys(self._labels, False)
        ir_config = config.ir if config.ir is not None and config.ir.enabled else None
        self._ir_receiver_count = len(ir_config.rx) if ir_config is not None else 0
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
        self._magnetometer = (
            _SimulatedMagnetometer()
            if config.magnetometer is not None and config.magnetometer.enabled
            else None
        )
        self._storage = (
            FakeDeviceStorage() if config.sdcard is not None and config.sdcard.enabled else None
        )
        self._radio_node = (
            config.radio.node if config.radio is not None and config.radio.enabled else None
        )
        self.power_on()

    def power_on(self) -> None:
        """Build ``hw`` afresh, as a reset does; the card, pins, sensors and recordings stay.

        The debouncer reads the pins as they stand, so a button held through
        it stays down without a new press. Strips are dark, no clip plays,
        the IR receivers and the radio have caught nothing, and the device
        speaks the Aura wire-frame until ``hw.ir.apply_codec``.
        """
        config = self._config
        self._ir_readers = [_SimulatedPulseReader() for _ in range(self._ir_receiver_count)]
        self._buttons = _ReadingButtons(
            [(label, self._pin_reader(label)) for label in self._labels],
            interval=_DEBOUNCE_INTERVAL,
            down=self._read_down,
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
        ir = self._build_ir() if self._ir_readers else None
        self._radio = _SimulatedRadioTransport(self) if self._radio_node is not None else None
        radio = RadioTransceiver(self._radio) if self._radio is not None else None
        self.hw = DeviceHardware(
            outputs=outputs,
            buttons=self._buttons,
            accelerometer=self._accelerometer,
            magnetometer=self._magnetometer,
            network_controls=HardwareNetworkControls(ir, radio),
            ir=ir,
            radio=radio,
            storage=self._storage,
            audio_registry=self._audio_registry,
        )

    def receive_ir(self, payload: bytes) -> None:
        """Land a clean shot carrying *payload* on every IR receiver.

        Encoded through the installed codec; the transceiver's next
        ``update`` decodes it. A device with no IR receiver catches nothing.
        """
        ir = self.hw.ir
        if ir is None:
            return
        encoder_class, _decoder_class = ir.codec
        self.land_ir(encoder_class().encode(payload))

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

    def land_radio(self, payload: bytes, sender: int) -> None:
        """Land a packet *sender* sent, for the transceiver's next free ``update`` to read."""
        self._require_radio().waiting.append((sender, payload))

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

    def registered(self, button: str) -> bool:
        """Whether every scheduled change of *button* has landed and the debouncer reads it.

        A change that lands as the device boots registers without an edge:
        the new debouncer reads the pin as it stands.
        """
        return not self._pin_changes[button] and self._read_down[button] == self._pressed[button]

    def accelerate(self, x: float, y: float, z: float) -> None:
        self._require_accelerometer().hold(x, y, z)

    def move(self, strength: float = DEFAULT_SWAY_STRENGTH) -> None:
        """Sway *strength* m/s² either side of the held reading on x."""
        self._require_accelerometer().sway(strength)

    def hold_still(self) -> None:
        self._require_accelerometer().rest()

    def magnetize(self, x: float, y: float, z: float) -> None:
        self._require_magnetometer().magnetic = (x, y, z)

    def hold(self, *buttons: str) -> None:
        """Schedule a press of every one of *buttons*, all at the same moment."""
        self._schedule(buttons, True)

    def release(self, *buttons: str) -> None:
        """Schedule a release of every one of *buttons*, all at the same moment."""
        self._schedule(buttons, False)

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
        self.radio_sent.clear()
        self.played.clear()
        self.buzzed.clear()

    def _build_ir(self) -> InfraredTransceiver:
        """Assemble the real IR stack the way ``device_builder`` does, on simulated pulses."""
        gate = IrTransmitGate()
        receiver = InfraredReceiver(list(self._ir_readers), AuraInfraredDecoder, gate)
        self._ir_receiver = receiver
        encoder = AuraInfraredEncoder()
        transmitters = {
            emitter: InfraredTransmitter(_SimulatedPulseWriter(self, emitter), encoder, gate)
            for emitter in self._wired_emitters
        }
        return InfraredTransceiver(transmitters, receiver, gate)

    def _emit(self, emitter: str, pulses: array | list[int]) -> None:
        """Record what *emitter* carried, let the device's own readers see it, and hand it on."""
        self.ir_sent.append(IrSent(self.now(), emitter, self._decode_wire(pulses)))
        self.land_ir(pulses)
        if self._ir_sink is not None:
            self._ir_sink(emitter, list(pulses))

    def _send_radio(self, payload: bytes) -> None:
        self.radio_sent.append(RadioSent(self.now(), payload))
        if self._radio_sink is not None:
            self._radio_sink(payload)

    def _decode_wire(self, pulses: array | list[int]) -> bytes:
        """The payload *pulses* carry, read back through the installed codec."""
        ir = self.hw.ir
        assert ir is not None  # only an assembled transceiver's emitters emit
        _encoder_class, decoder_class = ir.codec
        decoder = decoder_class()
        for pulse in pulses:
            payload = decoder.decode(pulse)
            if payload is not None:
                return bytes(payload)
        raise ValueError(f"the {decoder.__class__.__name__} cannot read back what was sent")

    def _require_radio(self) -> _SimulatedRadioTransport:
        if self._radio is None:
            raise ValueError("the config declares no radio")
        return self._radio

    def _require_accelerometer(self) -> _SimulatedAccelerometer:
        if self._accelerometer is None:
            raise ValueError("the config declares no accelerometer")
        return self._accelerometer

    def _require_magnetometer(self) -> _SimulatedMagnetometer:
        if self._magnetometer is None:
            raise ValueError("the config declares no magnetometer")
        return self._magnetometer

    def _schedule(self, buttons: tuple[str, ...], pressed: bool) -> None:
        # Queued behind the previous change of every button, so back-to-back
        # calls never land inside the debounce window and get swallowed.
        at = max([self.now(), *(self._pin_free_at[button] for button in buttons)])
        for button in buttons:
            self._pin_changes[button].append((at, pressed))
            self._pin_free_at[button] = at + _PIN_SETTLE

    def _pin_reader(self, label: str) -> Callable[[], bool]:
        return lambda: not self._pressed[label]  # pull-up: HIGH means not pressed
