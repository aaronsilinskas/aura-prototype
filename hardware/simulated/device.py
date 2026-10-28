"""The Simulated device: scripted pins in, recorded outputs out.

It boots through the Device assembly, as a board does, with ``SimulatedParts``
standing in for the hardware, so it builds, skips, rejects and narrates a
``DeviceConfig`` exactly as a board would: a section that needs a disabled bus
is rejected, and so is an enabled matrix entry (there is no simulated matrix).
Pin names and buses are otherwise ignored. It obeys the hardware import
contract: it knows nothing about scenes, the engine loop, or time beyond the
``now`` it is handed.

What the assembly builds is real wherever it can be: a real ``DebouncedButtons``
over scripted pins, a real ``VoicePool`` behind the recording audio, the real
``InfraredTransceiver`` over simulated pulse readers and writers, and the real
``RadioTransceiver`` over a simulated radio chip. An enabled ``sdcard`` section
is an in-memory card.

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

from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from engine.log import Logger
from engine.state import ScopeValue
from hardware.shared.debounced_buttons import DEBOUNCE_INTERVAL
from hardware.shared.device_assembly import assemble_device, button_label
from hardware.shared.device_config import DeviceConfig
from hardware.simulated.simulated_parts import (
    DEFAULT_SWAY_STRENGTH,
    SimulatedAccelerometer,
    SimulatedMagnetometer,
    SimulatedParts,
    SimulatedRadioTransport,
    wav_length,
)

__all__ = [
    "DEFAULT_SWAY_STRENGTH",
    "Buzzed",
    "IrSent",
    "Played",
    "RadioSent",
    "SimulatedHardware",
    "Strip",
]

_PIN_SETTLE = 2 * DEBOUNCE_INTERVAL
"""How long a scripted pin level holds before the next change may start.

Long enough for the debouncer to commit it, so every scripted press and
release registers and tests never need to know the debounce interval.
"""


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


class SimulatedHardware:
    """A Simulated device: ``hw`` is the ``DeviceHardware`` a scene boots on.

    *now* reads the simulation clock; every recording is stamped with it, and
    scripted pin changes fall due against it. Call ``settle_pins`` once per
    tick, before the tick reads the buttons. *ir_sink*, when given, is handed
    every emitter write as ``(emitter, pulses)``, and *radio_sink* every radio
    send's payload. *logger*, when given, narrates every boot; without one the
    device is silent.

    ``power_on`` resets the device: see there for what it rebuilds.

    Raises:
        RuntimeError: If the config is one the Device assembly rejects.
        ValueError: If the config has an enabled matrix pixel entry.
    """

    def __init__(
        self,
        now: Callable[[], float],
        config: DeviceConfig,
        ir_sink: Callable[[str, list[int]], None] | None = None,
        radio_sink: Callable[[bytes], None] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.now = now
        self._config = config
        self._ir_sink = ir_sink
        self._radio_sink = radio_sink
        self._logger = logger
        self.ir_sent: list[IrSent] = []
        self.radio_sent: list[RadioSent] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        # Which button each pin is, so a scripted press of a label reaches its pin.
        self._button_of_pin = {name: button_label(i) for i, name in enumerate(config.buttons)}
        labels = self._button_of_pin.values()
        self._pressed = dict.fromkeys(labels, False)
        self._pin_changes: dict[str, list[tuple[float, bool]]] = {b: [] for b in labels}
        self._pin_free_at = dict.fromkeys(labels, 0.0)
        self._boot(SimulatedParts(self))

    def power_on(self) -> None:
        """Boot through the Device assembly afresh, as a reset does.

        The card, the sensors, the pins and the recordings stay; everything
        else is rebuilt. The debouncer reads the pins as they stand, so a
        button held through it stays down without a new press. Strips are
        dark, no clip plays, the IR receivers and the radio have caught
        nothing, and the device speaks the Aura wire-frame until
        ``hw.ir.apply_codec``.
        """
        self._boot(SimulatedParts(self, previous=self._parts))

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
        built = self._parts.ir_readers
        readers = built if receivers is None else [built[i] for i in receivers]
        for reader in readers:
            reader.capture(pulses)

    def land_radio(self, payload: bytes, sender: int) -> None:
        """Land a packet *sender* sent, for the transceiver's next free ``update`` to read."""
        self._require_radio().waiting.append((sender, payload))

    @property
    def ir_emitters(self) -> tuple[str, ...]:
        """The emitters the assembly wired, in ``IR_EMITTERS`` order."""
        return tuple(self._parts.ir_emitters)

    @property
    def ir_receiver_count(self) -> int:
        return len(self._parts.ir_readers)

    @property
    def best_receiver(self) -> int | None:
        """Index of the IR receiver the multi-receiver picked for the latest shot.

        ``None`` before any shot, or with fewer than two receivers, where
        there is no pick to make.
        """
        ir = self.hw.ir
        best = ir.last_best_receiver if ir is not None else None
        readers = self._parts.ir_readers
        return next((i for i, reader in enumerate(readers) if reader is best), None)

    def clip_length(self, clip: str) -> float:
        """Seconds *clip* plays for, read from the WAV header it plays from."""
        registry = self.hw.audio_registry
        if registry is None:
            raise ValueError("the config declares no audio")
        return wav_length(registry.path(clip))

    def is_playing(self, clip: str) -> bool:
        audio = self._parts.audio
        return audio is not None and audio.is_clip_playing(clip)

    def registered(self, button: str) -> bool:
        """Whether every scheduled change of *button* has landed and the debouncer reads it.

        A change that lands as the device boots registers without an edge:
        the new debouncer reads the pin as it stands.
        """
        return (
            not self._pin_changes[button]
            and self.hw.buttons.is_down(button) == self._pressed[button]
        )

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
        frames = [s.frames[key] for s in self._parts.strips if key in s.frames]
        if len(frames) != 1:
            raise KeyError(f"{len(frames)} strips show scope '{key}'; expected exactly one")
        return Strip(frames[0])

    def forget(self) -> None:
        self.ir_sent.clear()
        self.radio_sent.clear()
        self.played.clear()
        self.buzzed.clear()

    def _boot(self, parts: SimulatedParts) -> None:
        self._parts = parts
        self.hw = assemble_device(self._config, parts, self._logger)

    # -- what the device's parts report (see SimulatedParts) -------------------

    def on_ir_written(self, emitter: str, pulses: array | list[int]) -> None:
        """Record what *emitter* carried, let the device's own readers see it, and hand it on."""
        self.ir_sent.append(IrSent(self.now(), emitter, self._decode_wire(pulses)))
        self.land_ir(pulses)
        if self._ir_sink is not None:
            self._ir_sink(emitter, list(pulses))

    def on_clip_played(self, clip: str) -> None:
        self.played.append(Played(self.now(), clip))

    def on_buzzed(self, pattern: tuple[int, ...]) -> None:
        self.buzzed.append(Buzzed(self.now(), pattern))

    def on_radio_sent(self, payload: bytes) -> None:
        self.radio_sent.append(RadioSent(self.now(), payload))
        if self._radio_sink is not None:
            self._radio_sink(payload)

    def pin_level(self, pin: str) -> bool:
        """The raw level of button *pin*: pulled up, so HIGH (``True``) means not pressed."""
        return not self._pressed[self._button_of_pin[pin]]

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

    def _require_radio(self) -> SimulatedRadioTransport:
        radio = self._parts.radio
        if radio is None:
            raise ValueError("the config declares no radio")
        return radio

    def _require_accelerometer(self) -> SimulatedAccelerometer:
        accelerometer = self.hw.accelerometer
        if accelerometer is None:
            raise ValueError("the config declares no accelerometer")
        assert isinstance(accelerometer, SimulatedAccelerometer)
        return accelerometer

    def _require_magnetometer(self) -> SimulatedMagnetometer:
        magnetometer = self.hw.magnetometer
        if magnetometer is None:
            raise ValueError("the config declares no magnetometer")
        assert isinstance(magnetometer, SimulatedMagnetometer)
        return magnetometer

    def _schedule(self, buttons: tuple[str, ...], pressed: bool) -> None:
        # Queued behind the previous change of every button, so back-to-back
        # calls never land inside the debounce window and get swallowed.
        at = max([self.now(), *(self._pin_free_at[button] for button in buttons)])
        for button in buttons:
            self._pin_changes[button].append((at, pressed))
            self._pin_free_at[button] = at + _PIN_SETTLE
