"""PROTOTYPE (#957), throwaway: the Simulation test harness half of the stub.

Boots a *real* scene through ``build_scene_runtime`` on a
``SimulatedHardware`` and drives every device on one shared fixed-step clock.
It lives under ``app/`` because booting a scene needs the composition layer,
which the hardware import contract keeps out of ``hardware/``.

Shortcuts a real build must not take (each is a finding, see the ticket):

- The per-tick loop below is a copy of ``run_scene``'s body; #958 extracts it.
- The fixed-step clock is swapped in by patching ``Timer`` during the build,
  because ``build_scene_runtime`` constructs its own ``Timer`` with no seam.
- Scene-data overrides are applied by poking the registry's private entry.
- The IR medium does not exist: ``receive_ir`` injects straight into a device.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest import mock

import app.scene_composition as composition
from app.scene_composition import build_scene_runtime, scan_boot_scene_registry
from engine.input import ButtonData, InputEvents
from engine.network import NetworkEvents
from engine.state import ScopeValue
from engine.timer import Timer
from hardware.simulated_prototype.device import (
    Buzzed,
    IrSent,
    Played,
    SimulatedHardware,
    Strip,
)

TICK = 1 / 60
"""Fixed simulation step. Every device in a ``Simulation`` ticks on it in lockstep."""


class _SimClock(Timer):
    def update(self) -> None:
        self.elapsed = TICK
        self.total += TICK


class Simulation:
    """One shared clock and every simulated device on it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.devices: list[SimulatedDevice] = []

    def add_device(self, name: str, scene: str, scene_data: dict | None = None) -> SimulatedDevice:
        device = SimulatedDevice(self, name, scene, scene_data or {})
        self.devices.append(device)
        return device

    def advance(self, seconds: float) -> None:
        """Tick every device in lockstep until *seconds* of sim time have passed."""
        end = self.now + seconds - TICK / 2
        while self.now < end:
            self.now += TICK
            for device in self.devices:
                device._tick()

    def run_until(self, condition: Callable[[], bool], timeout: float = 10.0) -> None:
        """Tick until *condition* holds; fail loudly after *timeout* sim seconds."""
        deadline = self.now + timeout
        while not condition():
            if self.now >= deadline:
                raise AssertionError(f"condition not met within {timeout}s of sim time")
            self.advance(TICK)


class SimulatedDevice:
    """A simulated device running a real scene: the handle a test talks to."""

    def __init__(self, sim: Simulation, name: str, scene: str, scene_data: dict) -> None:
        self.name = name
        self._sim_hw = SimulatedHardware(now=lambda: sim.now)
        registry = scan_boot_scene_registry(None)
        entry = registry._scenes[scene]  # PROTOTYPE: no override seam exists
        entry.initial_data = {**(entry.initial_data or {}), **scene_data}
        with mock.patch.object(composition, "Timer", _SimClock):
            self._runtime = build_scene_runtime(self._sim_hw.hw, scene, scene_registry=registry)
        self._ir_inbox: list[NetworkEvents.IRReceived] = []
        self._button_data = ButtonData({})
        self._input_event = InputEvents.Sensors(self._button_data, None, None)

    # -- inputs -------------------------------------------------------------

    def tap(self, button: str, hold_for: float = 0.1) -> None:
        """Press *button* now and let go after *hold_for* sim seconds."""
        self._sim_hw.tap(button, hold_for)

    def hold(self, button: str) -> None:
        self._sim_hw.hold(button)

    def release(self, button: str) -> None:
        self._sim_hw.release(button)

    def receive_ir(self, payload: bytes, signal_strength: int = 100, error_margin: int = 0) -> None:
        """Deliver an IR packet on the next tick, as if a receiver decoded it."""
        self._ir_inbox.append(
            NetworkEvents.IRReceived(payload, signal_strength, error_margin, best_receiver=None)
        )

    # -- queries ------------------------------------------------------------

    @property
    def ir_sent(self) -> list[IrSent]:
        return self._sim_hw.ir_sent

    @property
    def played(self) -> list[Played]:
        return self._sim_hw.played

    @property
    def buzzed(self) -> list[Buzzed]:
        return self._sim_hw.buzzed

    def strip(self, scope: ScopeValue) -> Strip:
        return self._sim_hw.strip(scope)

    def has_played(self, clip: str) -> bool:
        return any(p.clip == clip for p in self.played)

    def forget(self) -> None:
        """Drop everything recorded so far, so later asserts see only what follows."""
        self._sim_hw.forget()

    # -- loop ---------------------------------------------------------------

    def _tick(self) -> None:
        self._sim_hw.settle_pins()
        # PROTOTYPE: copy of run_scene's per-tick body; #958 shares the real one.
        runtime = self._runtime
        self._sim_hw.hw.buttons.update(TICK, self._button_data)
        active_state = runtime.manager.active_state
        if active_state is not None:
            for event in self._ir_inbox:
                active_state.queue_event(event)
            active_state.queue_event(self._input_event)
        self._ir_inbox.clear()
        runtime.manager.update()
        runtime.effect_manager.update(runtime.timer)
