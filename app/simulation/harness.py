"""The Simulation test harness: real scenes on simulated devices, one shared clock.

Boots each device's scene through ``build_scene_runtime`` and drives it with
the same ``build_scene_tick`` body the board runs. It lives under ``app/``
because booting a scene needs the composition layer, which the hardware import
contract keeps out of ``hardware/``.
"""

from __future__ import annotations

from collections.abc import Callable

from app.scene_composition import build_scene_runtime, build_scene_tick, scan_boot_scene_registry
from engine.network import NetworkEvents
from engine.state import ScopeValue
from engine.timer import Timer
from hardware.simulated.device import Buzzed, IrSent, Played, SimulatedHardware, Strip

__all__ = ["TICK", "SimulatedDevice", "Simulation"]

TICK = 1 / 60
"""Fixed simulation step. Every device in a ``Simulation`` ticks on it in lockstep."""


class _SimulationClock(Timer):
    """A device's engine clock, read straight off the ``Simulation``'s ``now``.

    Every device and its recordings share one timeline, even a device added
    after the simulation has already advanced.
    """

    __slots__ = ("_sim",)

    def __init__(self, sim: Simulation) -> None:
        super().__init__()
        self._sim = sim

    def update(self) -> None:
        self.elapsed = TICK
        self.total = self._sim.now


class Simulation:
    """One shared clock and every simulated device on it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.devices: list[SimulatedDevice] = []

    def add_device(
        self, name: str, scene: str, scene_data: dict[str, object] | None = None
    ) -> SimulatedDevice:
        """Boot *scene* on a new simulated device; *scene_data* overrides its tunables."""
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
        """Tick until *condition* holds; fail after *timeout* sim seconds."""
        deadline = self.now + timeout
        while not condition():
            if self.now >= deadline:
                raise AssertionError(f"condition not met within {timeout}s of sim time")
            self.advance(TICK)


class SimulatedDevice:
    """A simulated device running a real scene: the handle a test talks to."""

    def __init__(
        self, sim: Simulation, name: str, scene: str, scene_data: dict[str, object]
    ) -> None:
        self.name = name
        self._sim_hw = SimulatedHardware(now=lambda: sim.now)
        hw = self._sim_hw.hw
        registry = scan_boot_scene_registry(hw.storage)
        if scene_data:
            registry.override_initial_data(scene, scene_data)
        self._runtime = build_scene_runtime(
            hw, scene, scene_registry=registry, timer=_SimulationClock(sim)
        )
        self._scene_tick = build_scene_tick(hw, self._runtime)
        self._ir_inbox: list[NetworkEvents.IRReceived] = []

    # -- inputs -------------------------------------------------------------

    def tap(self, button: str) -> None:
        """Press and release *button*, each long enough to register."""
        self._sim_hw.tap(button)

    def hold(self, button: str) -> None:
        """Press *button* and keep it down until ``release``."""
        self._sim_hw.hold(button)

    def release(self, button: str) -> None:
        self._sim_hw.release(button)

    def receive_ir(self, payload: bytes) -> None:
        """Deliver a clean, full-strength IR packet on the next tick, as if decoded."""
        self._ir_inbox.append(NetworkEvents.IRReceived(payload, 100, 0, best_receiver=None))

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
        """Drop everything recorded so far, so later asserts see only what follows.

        Strips keep showing their current frame; only the event records clear.
        """
        self._sim_hw.forget()

    # -- loop ---------------------------------------------------------------

    def _tick(self) -> None:
        self._sim_hw.settle_pins()
        active_state = self._runtime.manager.active_state
        if active_state is not None:
            for event in self._ir_inbox:
                active_state.queue_event(event)
        self._ir_inbox.clear()
        self._scene_tick()
