"""PROTOTYPE (#957), throwaway: the Simulated device half of the stub harness.

A board-free ``DeviceHardware`` whose button pins are scripted and whose
outputs record what a real device would show, play, buzz and send. It lives
under ``hardware/`` and obeys the hardware import contract: it knows nothing
about scenes, the engine loop or time beyond the ``now`` it is handed.

Shortcuts a real build must not take:

- Every leaf scope is one fixed 10-pixel strip (no device profile/config).
- Audio clips never finish (no clip durations), so ``stops_effect`` effects
  such as ``scene.fire_shot`` never end on their own.
- No IR or radio transceiver: ``send_ir`` only records.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from effects.effect import Effect, PixelBuffer
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt, NetworkControls, Scope, ScopeValue
from hardware.shared.debounced_buttons import DebouncedButtons
from hardware.shared.device_hardware import DeviceHardware

PIXELS_PER_SCOPE = 10

_LEAF_SCOPES = [
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.AMBIENT,
    Scope.Global.MAIN,
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
]


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
    pattern: tuple


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
        self._sim_hw.radio_sent.append((self._sim_hw.now(), bytes(data)))


class _RecordingOutput(EffectOutput):
    """One output covering every leaf scope: records frames, clips and haptics."""

    def __init__(self, sim_hw: SimulatedHardware) -> None:
        super().__init__()
        self._sim_hw = sim_hw
        self.min_resolution = PIXELS_PER_SCOPE
        self.scopes = _LEAF_SCOPES
        self.frames: dict[str, list[int]] = {}

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(PIXELS_PER_SCOPE)

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        self.frames[scope_key] = list(buffer)

    def clear_pixels(self, scope_key: str) -> None:
        self.frames[scope_key] = [0] * PIXELS_PER_SCOPE

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        now = self._sim_hw.now()
        if effect.audio is not None:
            clip = effect.audio.clips.get(event.verb)
            if clip is not None:
                self._sim_hw.played.append(Played(now, clip.name))
        if effect.haptic is not None:
            pattern = effect.haptic.patterns.get(event.verb)
            if pattern is not None:
                self._sim_hw.buzzed.append(Buzzed(now, tuple(pattern.sequence)))


class SimulatedHardware:
    """Scripted pins in, recorded outputs out, wrapped around a real ``DeviceHardware``."""

    def __init__(self, now: Callable[[], float]) -> None:
        self.now = now
        self.ir_sent: list[IrSent] = []
        self.radio_sent: list[tuple[float, bytes]] = []
        self.played: list[Played] = []
        self.buzzed: list[Buzzed] = []
        self._pins: dict[str, bool] = {"A": False, "B": False}  # True = held down
        self._release_at: dict[str, float] = {}
        self._output = _RecordingOutput(self)
        self.hw = DeviceHardware(
            outputs=[self._output],
            buttons=DebouncedButtons([(label, self._pin_reader(label)) for label in self._pins]),
            accelerometer=None,
            magnetometer=None,
            network_controls=_RecordingNetwork(self),
            ir=None,
            radio=None,
            storage=None,
            audio_registry=None,
        )

    def tap(self, button: str, hold_for: float) -> None:
        self._pins[button] = True
        self._release_at[button] = self.now() + hold_for

    def hold(self, button: str) -> None:
        self._pins[button] = True
        self._release_at.pop(button, None)

    def release(self, button: str) -> None:
        self._pins[button] = False

    def settle_pins(self) -> None:
        """Let go of any tapped button whose hold time is up. Called once per tick."""
        for button, at in list(self._release_at.items()):
            if self.now() >= at:
                self._pins[button] = False
                del self._release_at[button]

    def strip(self, scope: ScopeValue) -> Strip:
        (key,) = scope.keys
        return Strip(self._output.frames.get(key, [0] * PIXELS_PER_SCOPE))

    def forget(self) -> None:
        self.ir_sent.clear()
        self.radio_sent.clear()
        self.played.clear()
        self.buzzed.clear()

    def _pin_reader(self, label: str) -> Callable[[], bool]:
        return lambda: not self._pins[label]  # pull-up: HIGH means not pressed
