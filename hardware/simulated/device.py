"""The Simulated device: scripted pins in, recorded outputs out.

Builds a real ``DeviceHardware`` around a real ``DebouncedButtons`` and a real
``VoicePool``, so input debouncing and clip-driven effect endings behave as on
a board. It obeys the hardware import contract: it knows nothing about scenes,
the engine loop, or time beyond the ``now`` it is handed.

Only what the Tag shooting scenario needs is simulated: every leaf scope is
one fixed strip, and there is no IR or radio transceiver (``send_ir`` only
records, and incoming IR is injected by the harness).
"""

from __future__ import annotations

import wave
from collections.abc import Callable
from dataclasses import dataclass

from effects.effect import Effect, PixelBuffer
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt, NetworkControls, Scope, ScopeValue
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.voice_pool import VoicePool, VoiceSink

__all__ = ["PIXELS_PER_SCOPE", "Buzzed", "IrSent", "Played", "SimulatedHardware", "Strip"]

PIXELS_PER_SCOPE = 10

_LEAF_SCOPES = [
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
    Scope.Global.MAIN,
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
]

_BUTTONS: tuple[str, ...] = ("A", "B")
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


class _RecordingPixels(EffectOutput):
    """One pixel output covering every leaf scope; keeps each scope's latest frame."""

    def __init__(self) -> None:
        super().__init__()
        self.min_resolution = PIXELS_PER_SCOPE
        self.scopes = _LEAF_SCOPES
        self.frames: dict[str, list[int]] = {}

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(PIXELS_PER_SCOPE)

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        self.frames[scope_key] = list(buffer)

    def clear_pixels(self, scope_key: str) -> None:
        self.frames[scope_key] = [0] * PIXELS_PER_SCOPE


class _SimulatedAudio(EffectOutput, VoiceSink):
    """Plays clips on a real ``VoicePool``; a clip "plays" for its WAV's length.

    Mirrors ``AudioEffectOutput``'s claim rule, so a ``stops_effect`` clip ends
    its effect when the clip runs out, exactly as on a board.
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
        audio_only = effect.pixels is None and effect.haptic is None
        stops_receipt = audio_only or config.stops_effect
        path = self._registry.path(config.name)
        if self._pool.claim(self, path, config.loop, stops_receipt, receipt) != -1:
            self._sim_hw.played.append(Played(self._sim_hw.now(), config.name))

    def flush(self) -> None:
        self._pool.sweep(self)

    def open_source(self, path: str) -> object | None:
        with wave.open(path, "rb") as clip:
            return clip.getnframes() / clip.getframerate()

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


class SimulatedHardware:
    """A Simulated device: ``hw`` is the ``DeviceHardware`` a scene boots on.

    *now* reads the simulation clock; every recording is stamped with it, and
    scripted pin changes fall due against it. Call ``settle_pins`` once per
    tick, before the tick reads the buttons.
    """

    def __init__(self, now: Callable[[], float], voices: int = 2) -> None:
        self.now = now
        self.ir_sent: list[IrSent] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        self._pressed = dict.fromkeys(_BUTTONS, False)
        self._pin_changes: dict[str, list[tuple[float, bool]]] = {b: [] for b in _BUTTONS}
        self._pin_free_at = dict.fromkeys(_BUTTONS, 0.0)
        self._pixels = _RecordingPixels()
        audio_registry = AudioRegistry()
        self.hw = DeviceHardware(
            outputs=[
                self._pixels,
                _SimulatedAudio(self, audio_registry, voices),
                _RecordingHaptic(self),
            ],
            buttons=DebouncedButtons(
                [(label, self._pin_reader(label)) for label in _BUTTONS],
                interval=_DEBOUNCE_INTERVAL,
            ),
            accelerometer=None,
            magnetometer=None,
            network_controls=_RecordingNetwork(self),
            ir=None,
            radio=None,
            storage=None,
            audio_registry=audio_registry,
        )

    def tap(self, button: str) -> None:
        """Press and release *button*, each held long enough to register."""
        self.hold(button)
        self.release(button)

    def hold(self, button: str) -> None:
        """Press *button* and keep it down."""
        self._schedule(button, True)

    def release(self, button: str) -> None:
        """Let go of *button*."""
        self._schedule(button, False)

    def settle_pins(self) -> None:
        """Apply every scripted pin change that has fallen due."""
        now = self.now()
        for button, changes in self._pin_changes.items():
            while changes and changes[0][0] <= now:
                self._pressed[button] = changes.pop(0)[1]

    def strip(self, scope: ScopeValue) -> Strip:
        (key,) = scope.keys
        return Strip(self._pixels.frames.get(key, [0] * PIXELS_PER_SCOPE))

    def forget(self) -> None:
        """Drop everything recorded so far; strips keep their current frame."""
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
