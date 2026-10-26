"""The Simulated device: scripted pins in, recorded outputs out.

Builds a real ``DeviceHardware`` around a real ``DebouncedButtons`` and a real
``VoicePool``, so input debouncing and clip-driven effect endings behave as on
a board. It obeys the hardware import contract: it knows nothing about scenes,
the engine loop, or time beyond the ``now`` it is handed.

Its shape comes from a ``DeviceConfig``: one button per declared pin, labelled
``A`` onward as on a board; one recording pixel output per NeoPixel strip; the
declared voice count; a haptic output when ``haptics`` is declared. Wiring
(pins, buses, addresses) is ignored. Matrix pixels, sensors, and the IR and
radio transceivers are not simulated (``send_ir`` only records, and incoming
IR is injected by the harness).
"""

from __future__ import annotations

import wave
from collections.abc import Callable
from dataclasses import dataclass

from effects.effect import Effect, PixelBuffer
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.input import ButtonData
from engine.state import EffectReceipt, NetworkControls, Scope, ScopeValue
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_config import DeviceConfig, MatrixPixelsConfig
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.voice_pool import VoicePool, VoiceSink, clip_stops_receipt

__all__ = ["Buzzed", "IrSent", "Played", "SimulatedHardware", "Strip"]

_DEBOUNCE_INTERVAL = 0.05
_PIN_SETTLE = 2 * _DEBOUNCE_INTERVAL
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
class Played:
    at: float
    clip: str


@dataclass(frozen=True)
class Buzzed:
    at: float
    pattern: tuple[int, ...]


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

    def __repr__(self) -> str:
        return "Strip(" + " ".join(f"{p:06X}" for p in self.pixels) + ")"


class _RecordingNetwork(NetworkControls):
    def __init__(self, sim_hw: SimulatedHardware) -> None:
        self._sim_hw = sim_hw

    def send_ir(self, data: bytes, emitter: str) -> None:
        self._sim_hw.ir_sent.append(IrSent(self._sim_hw.now(), emitter, bytes(data)))

    def send_radio(self, data: bytes) -> None:
        pass


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
        self._ends_at: list[float | None] = [None] * voices

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

    def flush(self) -> None:
        self._pool.sweep(self)

    def open_source(self, path: str) -> object | None:
        return _wav_length(path)

    def play(self, slot: int, source: object, loop: bool) -> None:
        assert isinstance(source, float)  # the clip length open_source returned
        self._ends_at[slot] = None if loop else self._sim_hw.now() + source

    def stop(self, slot: int) -> None:
        self._ends_at[slot] = None

    def set_loudness(self, slot: int, loudness: float) -> None:
        pass

    def is_playing(self, slot: int) -> bool:
        ends_at = self._ends_at[slot]
        return ends_at is not None and self._sim_hw.now() < ends_at


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


class _CountingButtons(DebouncedButtons):
    """The real debouncer, also counting each button's registered releases."""

    def __init__(self, buttons: list[tuple[str, Callable[[], bool]]], interval: float) -> None:
        super().__init__(buttons, interval=interval)
        self.releases = {label: 0 for label, _ in buttons}

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
    tick, before the tick reads the buttons.
    """

    def __init__(self, now: Callable[[], float], config: DeviceConfig) -> None:
        self.now = now
        self.ir_sent: list[IrSent] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        labels = [chr(ord("A") + i) for i in range(len(config.buttons))]
        self._pressed = dict.fromkeys(labels, False)
        self._pin_changes: dict[str, list[tuple[float, bool]]] = {b: [] for b in labels}
        self._pin_free_at = dict.fromkeys(labels, 0.0)
        self._buttons = _CountingButtons(
            [(label, self._pin_reader(label)) for label in labels], interval=_DEBOUNCE_INTERVAL
        )
        self._strips = [_RecordingPixels(segments) for segments in _strip_segments(config)]
        self._audio_registry = AudioRegistry()
        outputs: list[EffectOutput] = [*self._strips]
        if config.audio is not None and config.audio.enabled:
            outputs.append(_SimulatedAudio(self, self._audio_registry, config.audio.voices))
        if config.haptics is not None and config.haptics.enabled:
            outputs.append(_RecordingHaptic(self))
        self.hw = DeviceHardware(
            outputs=outputs,
            buttons=self._buttons,
            accelerometer=None,
            magnetometer=None,
            network_controls=_RecordingNetwork(self),
            ir=None,
            radio=None,
            storage=None,
            audio_registry=self._audio_registry,
        )

    def clip_length(self, clip: str) -> float:
        """Seconds *clip* plays for, read from the WAV header it plays from."""
        return _wav_length(self._audio_registry.path(clip))

    def releases(self, button: str) -> int:
        """How many releases of *button* the debouncer has registered so far."""
        return self._buttons.releases[button]

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

    def _schedule(self, button: str, pressed: bool) -> None:
        # Queued behind the previous change, so back-to-back calls never land
        # inside the debounce window and get swallowed.
        at = max(self.now(), self._pin_free_at[button])
        self._pin_changes[button].append((at, pressed))
        self._pin_free_at[button] = at + _PIN_SETTLE

    def _pin_reader(self, label: str) -> Callable[[], bool]:
        return lambda: not self._pressed[label]  # pull-up: HIGH means not pressed
