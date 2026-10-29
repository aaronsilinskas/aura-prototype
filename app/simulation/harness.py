"""The Simulation test harness: real scenes on simulated devices, one shared clock.

Boots each device through the same ``build_scene_boot`` the board boots
through, and drives it with the ``build_scene_tick`` body that returns. It
lives under ``app/`` because booting a scene needs the composition layer,
which the hardware import contract keeps out of ``hardware/``.

A device's IR reaches its own receivers at once and other devices only through
the IR medium, where a test has aimed it: ``red.aim(LINE, at=blue)`` then
``red.tap("A")``. ``receive_ir`` stands in for a sender outside the simulation.
Its radio reaches every other device through the radio medium, with no aim;
``receive_radio`` stands in for an outside sender.

A device reboots as a board does (see ``SimulatedDevice``), so a test can
follow the lobby into a game and back.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from app.scene_composition import build_scene_boot
from engine.state import ScopeValue
from engine.timer import Timer
from hardware.shared.device_config import (
    DeviceConfig,
    parse_device_config,
    read_device_config_mapping,
)
from hardware.simulated.device import (
    DEFAULT_SWAY_STRENGTH,
    Buzzed,
    IrSent,
    Played,
    RadioSent,
    SimulatedHardware,
    Strip,
)

__all__ = ["TICK", "SimulatedDevice", "Simulation"]

TICK = 1 / 60
"""Fixed simulation step. Every device in a ``Simulation`` ticks on it in lockstep."""

_SIMULATED_DEVICE_CONFIG = (
    Path(__file__).resolve().parents[2] / "examples" / "aura-device.simulated.json"
)


def _simulated_device_config(sd_card: bool, radio_node: int) -> DeviceConfig:
    mapping = read_device_config_mapping(str(_SIMULATED_DEVICE_CONFIG))
    if not sd_card:
        # Deleting the key, not `enabled: false`, so nothing card-shaped is
        # built or narrated.
        del mapping["sdcard"]
    mapping["radio"]["node"] = radio_node
    return parse_device_config(mapping)


class _Reset(BaseException):
    """A simulated device's reset: unwinds the rest of its tick, as a real reset does.

    A ``BaseException``, so no ``except Exception`` in a rule can swallow it.
    """


def _reset() -> None:
    raise _Reset


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


@dataclass(frozen=True)
class _Reach:
    """One device an aim reaches, and which of its receivers."""

    device: SimulatedDevice
    receivers: tuple[int, ...] | None
    """Indexes of the receivers reached; ``None`` for every one."""


@dataclass(frozen=True)
class _InFlight:
    """Pulses one emitter wrote, on their way to where it was aimed when they were sent."""

    sender: SimulatedDevice
    reaches: tuple[_Reach, ...]
    pulses: list[int]


@dataclass(frozen=True)
class _RadioInFlight:
    """A packet one device sent, on its way to every device there was when it was sent."""

    sender: SimulatedDevice
    receivers: tuple[SimulatedDevice, ...]
    payload: bytes


class Simulation:
    """One shared clock, every simulated device on it, and the IR and radio media between them.

    The IR medium holds each device's aims and the pulses in flight. Pulses an
    emitter writes during one tick land on every device it is aimed at at the
    start of the next, before any device ticks, so the order devices were
    added in never decides who hears what. Shots from several senders on one
    tick queue in sender add order; nothing collides.

    The radio medium keeps the same time, with no aim: a packet sent during
    one tick lands at the start of the next on every device but its sender
    that was in the simulation when it was sent.
    Packets from several senders queue in sender add order, with no collision
    or loss, and a device reads one a tick.

    Use it with ``with``, or the shared ``simulation`` fixture, which closes
    it after the test.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.devices: list[SimulatedDevice] = []
        self._aims: dict[tuple[SimulatedDevice, str], tuple[_Reach, ...]] = {}
        self._in_flight: list[_InFlight] = []
        self._radio_in_flight: list[_RadioInFlight] = []
        self._temp_dir = tempfile.TemporaryDirectory(prefix="aura-simulation-")

    def __enter__(self) -> Simulation:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Remove the temporary directory this simulation owns."""
        self._temp_dir.cleanup()

    def add_device(
        self,
        name: str,
        scene: str,
        scene_data: dict[str, object] | None = None,
        sd_card: bool = True,
    ) -> SimulatedDevice:
        """Switch a new simulated device on into *scene*, its flash ``default_scene``.

        Every boot runs the scene the card names, else *scene*. *scene_data*
        overrides *scene*'s tunables on every boot. The device's card starts
        empty; with *sd_card* false it has none, and never reboots. Its radio
        node is its place in add order, from 1.
        """
        radio_node = len(self.devices) + 1
        device = SimulatedDevice(self, name, scene, scene_data or {}, sd_card, radio_node)
        self.devices.append(device)
        return device

    def advance(self, seconds: float) -> None:
        """Tick every device in lockstep until *seconds* of sim time have passed."""
        end = self.now + seconds - TICK / 2
        while self.now < end:
            self.now += TICK
            self._land_in_flight_ir()
            self._land_in_flight_radio()
            for device in self.devices:
                device._tick()

    def run_until(self, condition: Callable[[], bool], timeout: float = 10.0) -> None:
        """Tick until *condition* holds; fail after *timeout* sim seconds."""
        deadline = self.now + timeout
        while not condition():
            if self.now >= deadline:
                raise AssertionError(f"condition not met within {timeout}s of sim time")
            self.advance(TICK)

    def _aim(
        self,
        sender: SimulatedDevice,
        emitter: str,
        devices: Sequence[SimulatedDevice],
        receivers: Sequence[int] | None,
    ) -> None:
        if emitter not in sender._sim_hw.ir_emitters:
            raise ValueError(f"{sender.name} has no {emitter!r} emitter wired")
        reach = None if receivers is None else tuple(receivers)
        reaches: list[_Reach] = []
        for device in dict.fromkeys(devices):
            if device is sender:
                raise ValueError(f"{sender.name} cannot aim at itself")
            if device._sim is not self:
                raise ValueError(f"{device.name} is in another Simulation")
            count = device._sim_hw.ir_receiver_count
            if reach is not None and any(not 0 <= i < count for i in reach):
                raise ValueError(f"{device.name} has receivers 0 to {count - 1}, not {reach}")
            reaches.append(_Reach(device, reach))
        self._aims[(sender, emitter)] = tuple(reaches)

    def _carry_ir(self, sender: SimulatedDevice, emitter: str, pulses: list[int]) -> None:
        """Put what *sender*'s *emitter* wrote into the medium, toward its aim as it stands now."""
        reaches = self._aims.get((sender, emitter), ())
        if reaches:
            self._in_flight.append(_InFlight(sender, reaches, pulses))

    def _carry_radio(self, sender: SimulatedDevice, payload: bytes) -> None:
        receivers = tuple(device for device in self.devices if device is not sender)
        self._radio_in_flight.append(_RadioInFlight(sender, receivers, payload))

    def _land_in_flight_radio(self) -> None:
        in_flight, self._radio_in_flight = self._radio_in_flight, []
        in_flight.sort(key=lambda packet: self.devices.index(packet.sender))
        for packet in in_flight:
            for device in packet.receivers:
                device._sim_hw.land_radio(packet.payload, packet.sender.radio_node)

    def _land_in_flight_ir(self) -> None:
        in_flight, self._in_flight = self._in_flight, []
        in_flight.sort(key=lambda shot: self.devices.index(shot.sender))
        for shot in in_flight:
            for reach in shot.reaches:
                reach.device._sim_hw.land_ir(shot.pulses, reach.receivers)


class SimulatedDevice:
    """A simulated device running a real scene: the handle a test talks to.

    It boots and ticks as a board does, through the same ``build_scene_boot``
    and ``build_scene_tick``; the scene it was switched on into stands in for
    the flash ``default_scene``. It reboots as a board does:
    ``DeviceSceneReboot`` persists the next scene to its card, then resets
    it. The reset abandons the rest of the tick, and the device boots at once,
    within that same tick, into whatever its card names; it ticks the new
    scene from the next.
    A reboot carries over the card, the pins, the accelerometer and
    magnetometer readings, its aims, the IR and radio media, its radio node,
    and the recordings; game state is gone, outputs are dark and silent, and
    packets it had not yet read are lost, as a real reset clears the radio
    chip.
    """

    def __init__(
        self,
        sim: Simulation,
        name: str,
        scene: str,
        scene_data: dict[str, object],
        sd_card: bool,
        radio_node: int,
    ) -> None:
        self.name = name
        self.radio_node = radio_node
        """The node this device sends as: its place in add order, from 1."""
        self._sim = sim
        self._switched_on_into = scene
        self._scene_data = scene_data
        self._sim_hw = SimulatedHardware(
            now=lambda: sim.now,
            config=_simulated_device_config(sd_card, radio_node),
            ir_sink=lambda emitter, pulses: sim._carry_ir(self, emitter, pulses),
            radio_sink=lambda payload: sim._carry_radio(self, payload),
        )
        self._boot()

    def _boot(self) -> None:
        """Boot through ``build_scene_boot``, the boot ``run_scene`` uses."""
        scene, self._scene_tick = build_scene_boot(
            self._sim_hw.hw,
            {"default_scene": self._switched_on_into},
            reset=_reset,
            timer=_SimulationClock(self._sim),
            scene_data={self._switched_on_into: self._scene_data} if self._scene_data else None,
        )
        self.scene = scene
        """The scene the device is running now."""

    # -- inputs -------------------------------------------------------------

    def tap(self, button: str) -> None:
        """Press and release *button*, advancing the simulation until both register.

        Every device ticks while it waits, as with ``Simulation.advance``.
        """
        self._sim_hw.hold(button)
        self._sim_hw.release(button)
        self._wait_until_registered((button,))

    def hold(self, *buttons: str) -> None:
        """Press every one of *buttons* together, kept down until ``release``.

        Advances the simulation until every press registers, ticking every
        device as ``Simulation.advance`` does.
        """
        self._sim_hw.hold(*buttons)
        self._wait_until_registered(buttons)

    def release(self, *buttons: str) -> None:
        """Release every one of *buttons* together, advancing until every release registers.

        A release that lands as the device reboots registers too: the scene
        that boots reads the button as up.
        """
        self._sim_hw.release(*buttons)
        self._wait_until_registered(buttons)

    def schedule_hold(self, *buttons: str) -> None:
        """Schedule a press of every one of *buttons* together; time does not advance.

        For presses on several devices on the same tick, which ``hold`` cannot
        give because it advances.
        """
        self._sim_hw.hold(*buttons)

    def schedule_release(self, *buttons: str) -> None:
        """Schedule a release of every one of *buttons* together; time does not advance."""
        self._sim_hw.release(*buttons)

    def _wait_until_registered(self, buttons: tuple[str, ...]) -> None:
        self._sim.run_until(lambda: all(self._sim_hw.registered(button) for button in buttons))

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

    def magnetize(self, x: float, y: float, z: float) -> None:
        """Hold the magnetometer's raw field at ``(x, y, z)`` µT, in the chip's own frame.

        It holds until changed; a device switches on reading a zero field.
        """
        self._sim_hw.magnetize(x, y, z)

    def aim(
        self,
        emitter: str,
        *,
        at: SimulatedDevice | Sequence[SimulatedDevice] | None,
        receivers: Sequence[int] | None = None,
    ) -> None:
        """Aim *emitter* at a device, at several, or (``None``) at nobody.

        The aim holds until replaced, and reaches the receivers at indexes
        *receivers* on each device, or every one. It applies to pulses sent
        from the next tick on; pulses already in the IR medium still land
        where they were aimed. A new device starts aimed at nobody.

        A device whose scene speaks another wire-frame codec can be aimed at:
        its decoder fails on the shot.

        Raises:
            ValueError: If this device does not wire *emitter*, *at* includes
                this device or one from another ``Simulation``, or
                *receivers* names an index a device lacks.
        """
        if at is None:
            devices: Sequence[SimulatedDevice] = ()
        elif isinstance(at, SimulatedDevice):
            devices = (at,)
        else:
            devices = at
        self._sim._aim(self, emitter, devices, receivers)

    def receive_ir(self, payload: bytes) -> None:
        """Land a clean shot carrying *payload* from a sender outside the ``Simulation``.

        Encoded with the scene's wire-frame codec and landed on every receiver
        at once, not through the IR medium. Decoded on the next tick, one shot
        per tick, unless the device's own send masks it.
        """
        self._sim_hw.receive_ir(payload)

    def receive_radio(self, payload: bytes, sender: int) -> None:
        """Land a packet carrying *payload* from node *sender*, outside the ``Simulation``.

        Not through the radio medium: it waits on this device's radio, read
        on the next tick, one packet per tick.
        """
        self._sim_hw.land_radio(payload, sender)

    # -- queries ------------------------------------------------------------

    @property
    def ir_sent(self) -> list[IrSent]:
        return self._sim_hw.ir_sent

    @property
    def radio_sent(self) -> list[RadioSent]:
        return self._sim_hw.radio_sent

    @property
    def played(self) -> list[Played]:
        return self._sim_hw.played

    @property
    def buzzed(self) -> list[Buzzed]:
        return self._sim_hw.buzzed

    @property
    def best_receiver(self) -> int | None:
        """Index of the IR receiver that decoded the latest shot best; ``None`` before any."""
        return self._sim_hw.best_receiver

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
        try:
            self._scene_tick()
        except _Reset:
            self._sim_hw.power_on()
            self._boot()
