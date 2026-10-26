"""The Simulation test harness: real scenes on simulated devices, one shared clock.

Boots each device's scene through ``build_scene_runtime`` and drives it with
the same ``build_scene_tick`` body the board runs. It lives under ``app/``
because booting a scene needs the composition layer, which the hardware import
contract keeps out of ``hardware/``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.scene_composition import (
    build_scene_runtime,
    build_scene_tick,
    resolve_ir_codec,
    scan_boot_scene_registry,
)
from engine.state import ScopeValue
from engine.timer import Timer
from hardware.shared.device_config import DeviceConfig, load_device_config
from hardware.simulated.device import (
    DEFAULT_SWAY_STRENGTH,
    Buzzed,
    IrSent,
    Played,
    SimulatedHardware,
    Strip,
)

__all__ = ["TICK", "SimulatedDevice", "Simulation"]

TICK = 1 / 60
"""Fixed simulation step. Every device in a ``Simulation`` ticks on it in lockstep."""

_SIMULATED_DEVICE_CONFIG = (
    Path(__file__).resolve().parents[2] / "examples" / "aura-device.simulated.json"
)


def _simulated_device_config() -> DeviceConfig:
    return load_device_config(str(_SIMULATED_DEVICE_CONFIG))


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
        self._sim = sim
        self._sim_hw = SimulatedHardware(now=lambda: sim.now, config=_simulated_device_config())
        hw = self._sim_hw.hw
        registry = scan_boot_scene_registry(hw.storage)
        if scene_data:
            registry.override_initial_data(scene, scene_data)
        self._sim_hw.apply_ir_codec(*resolve_ir_codec(registry, scene))
        self._runtime = build_scene_runtime(
            hw, scene, scene_registry=registry, timer=_SimulationClock(sim)
        )
        self._scene_tick = build_scene_tick(hw, self._runtime)

    # -- inputs -------------------------------------------------------------

    def tap(self, button: str) -> None:
        """Press and release *button*, advancing the simulation until both register.

        Every device ticks while it waits, as with ``Simulation.advance``.
        """
        released = self._sim_hw.releases(button)
        self._sim_hw.hold(button)
        self._sim_hw.release(button)
        self._sim.run_until(lambda: self._sim_hw.releases(button) > released)

    def hold(self, button: str) -> None:
        """Schedule a press of *button*, kept down until ``release``; time does not advance."""
        self._sim_hw.hold(button)

    def release(self, button: str) -> None:
        """Schedule a release of *button*; time does not advance."""
        self._sim_hw.release(button)

    def accelerate(self, x: float, y: float, z: float) -> None:
        """Hold the accelerometer at ``(x, y, z)`` m/s², for a jolt or a tilt.

        A held reading is not motion: a scene that tracks gravity reads it as a
        jolt that fades within a few ticks. Use ``move`` for sustained motion.
        """
        self._sim_hw.accelerate(x, y, z)

    def move(self, strength: float = DEFAULT_SWAY_STRENGTH) -> None:
        """Sway *strength* m/s² on top of the held reading, tick after tick until ``hold_still``."""
        self._sim_hw.move(strength)

    def hold_still(self) -> None:
        """Back to rest, with gravity on z, and stop any ``move``."""
        self._sim_hw.hold_still()

    def receive_ir(self, payload: bytes) -> None:
        """Land a clean shot carrying *payload* over the scene's wire-frame codec.

        Decoded on the next tick, one shot per tick, unless the device's own
        send masks it.
        """
        self._sim_hw.receive_ir(payload)

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

    def clip_length(self, clip: str) -> float:
        """Seconds *clip* plays for, read from the WAV header the device plays it from."""
        return self._sim_hw.clip_length(clip)

    def is_playing(self, clip: str) -> bool:
        """Whether *clip* is playing or looping now; false once it ran out or was stopped."""
        return self._sim_hw.is_playing(clip)

    def forget(self) -> None:
        """Drop everything recorded so far, so later asserts see only what follows.

        Strips keep showing their current frame; only the event records clear.
        """
        self._sim_hw.forget()

    # -- loop ---------------------------------------------------------------

    def _tick(self) -> None:
        self._sim_hw.settle_pins()
        self._scene_tick()
