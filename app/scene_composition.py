"""Board-free scene wiring — builds the engine/effect/scene machinery for one scene.

CPython-testable: imports only ``engine`` and the board-free modules under
``hardware.shared`` (``device_hardware``, ``ir_codecs``, ``ir_transceiver``,
``radio_transceiver``, ``scene_selection``). No ``TYPE_CHECKING`` guard is
needed because none of them carry board imports.
"""

from __future__ import annotations

import engine._path as _path
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData
from engine.log import Logger
from engine.namespace import ActiveSceneNamespace
from engine.network import NetworkEvents
from engine.pack_catalog import PackCatalog, scan_pack_roots
from engine.scene import SceneManager, SceneRegistry
from engine.state import SceneReboot
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs import codec_for
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_transceiver import InfraredTransceiver
from hardware.shared.radio_transceiver import RadioTransceiver
from hardware.shared.scene_selection import resolve_boot_scene

try:
    from collections.abc import Callable
except ImportError:
    pass  # collections.abc not available on all embedded runtimes

__all__ = [
    "SceneRuntime",
    "build_scene_boot",
    "build_scene_runtime",
    "build_scene_tick",
    "resolve_boot_scene_name",
    "resolve_ir_codec",
    "scan_boot_pack_catalog",
]


class SceneRuntime:
    """Bundle of the live objects a scene's per-tick loop drives.

    ``manager`` applies scene transitions, ``effect_manager`` renders the
    active scene's effects, ``timer`` tracks elapsed/total tick time, ``ir``
    is the device's ``InfraredTransceiver`` (``None`` on a device with no IR
    subsystem wired), and ``radio`` is the device's ``RadioTransceiver``
    (``None`` on a device with no radio peripheral wired) — both passed
    straight through from ``DeviceHardware``, no separate object built here.
    ``namespace`` is the Active scene namespace ``manager`` installs each
    scene into and ``effect_manager`` resolves names through.
    """

    __slots__ = ("effect_manager", "ir", "manager", "namespace", "radio", "timer")

    def __init__(
        self,
        manager: SceneManager,
        effect_manager: EffectManager,
        timer: Timer,
        ir: InfraredTransceiver | None,
        radio: RadioTransceiver | None,
        namespace: ActiveSceneNamespace,
    ) -> None:
        self.manager: SceneManager = manager
        self.effect_manager: EffectManager = effect_manager
        self.timer: Timer = timer
        self.ir: InfraredTransceiver | None = ir
        self.radio: RadioTransceiver | None = radio
        self.namespace: ActiveSceneNamespace = namespace


_TELEMETRY_PRINT_INTERVAL = 1.0  # seconds
_FLASH_PACKS_ROOT = "packs"
_CARD_PACKS_ROOT = "aura_packs"


def resolve_boot_scene_name(
    scene_registry: SceneRegistry,
    storage: DeviceStorage | None,
    settings_mapping: dict,
    logger: Logger | None = None,
) -> str:
    """Resolve the boot scene name and validate it against *scene_registry*.

    ``resolve_boot_scene`` decides only source precedence (persisted SD
    ``scene`` -> flash ``default_scene`` -> raise), never registry membership,
    so its result is validated here via ``SceneRegistry.resolve_known`` -- an unknown
    name, from either source, raises naming the known scenes. A ``None``
    *storage* is treated as no persisted override, leaving the flash
    ``default_scene`` to win.
    """
    scene_name = resolve_boot_scene(storage, settings_mapping, logger)
    return scene_registry.resolve_known(scene_name)


def resolve_ir_codec(
    scene_registry: SceneRegistry, scene_name: str
) -> tuple[type[InfraredEncoder], type[InfraredDecoder]]:
    """Return the encoder/decoder class pair of the wire-frame codec *scene_name* declares.

    Defaults to the ``"aura"`` codec when the scene declares none, and needs
    no built hardware to resolve.
    """
    return codec_for(scene_registry.ir_codec_for(scene_name))


def scan_boot_pack_catalog(
    storage: DeviceStorage | None,
    scene_data: dict[str, dict[str, object]] | None = None,
) -> PackCatalog:
    """Scan the device's pack roots into the one ``PackCatalog`` boot runs on.

    Flash ``packs`` always; the card's ``aura_packs`` only when *storage* is
    mounted and carries that folder. Call it after storage mounts.
    *scene_data* is passed through as the catalog's initial-data overrides.

    Raises:
        PackScanError: a pack or scene under either root is misconfigured.
    """
    roots = [_FLASH_PACKS_ROOT]
    if storage is not None:
        card_root = storage.path(_CARD_PACKS_ROOT)
        if _path.isdir(card_root):
            roots.append(card_root)
    return scan_pack_roots(roots, initial_data_overrides=scene_data)


def build_scene_runtime(
    hw: DeviceHardware,
    scene_name: str,
    catalog: PackCatalog,
    scene_reboot: SceneReboot | None = None,
    timer: Timer | None = None,
) -> SceneRuntime:
    """Wire the engine to *catalog*'s registries and load *scene_name* from it.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    the catalog's ``SceneRegistry``. The returned ``SceneRuntime`` has the
    resolved scene already active — the caller only needs to drive the
    per-tick loop.

    *catalog* is the one boot scan from ``scan_boot_pack_catalog``, shared
    with boot-scene and IR-codec resolution; nothing is scanned here.

    *scene_reboot*, if supplied, is the board-free ``SceneReboot`` port wired
    into ``SceneManager`` so rules can call ``state.scene_controls.reboot_into``/
    ``reboot_to_previous``. This function stays board-free, so it never
    constructs the live adapter itself -- ``build_scene_boot`` supplies it
    (see ``hardware.shared.device_reboot``). Omitted, a fresh base
    ``SceneReboot`` stands in, satisfying ``SceneManager``'s non-optional seam
    without pretending a reboot request can go anywhere.

    *timer*, if supplied, is the clock the whole runtime ticks on — the
    engine, the effects, and the debouncer via ``SceneRuntime.timer``. The
    Simulation test harness passes a fixed-step clock here; omitted, a
    wall-clock ``Timer`` is built.
    """
    effect_registry = catalog.effect_registry
    rule_registry = catalog.rule_registry
    scene_registry = catalog.scene_registry
    namespace = ActiveSceneNamespace(effect_registry, catalog.pack_sounds)
    effect_manager = EffectManager(namespace=namespace, outputs=hw.outputs)

    if timer is None:
        timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        network_controls=hw.network_controls,
        timer=timer,
    )

    manager = SceneManager(
        engine,
        effect_registry,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        namespace=namespace,
        scene_reboot=scene_reboot if scene_reboot is not None else SceneReboot(),
    )
    manager.load(scene_registry.resolve_known(scene_name))
    manager.update()  # applies the load transition; the scene is now active

    return SceneRuntime(
        manager=manager,
        effect_manager=effect_manager,
        timer=timer,
        ir=hw.ir,
        radio=hw.radio,
        namespace=namespace,
    )


def build_scene_boot(
    hw: DeviceHardware,
    settings_mapping: dict,
    reset: Callable[[], None],
    timer: Timer | None = None,
    logger: Logger | None = None,
    scene_data: dict[str, dict[str, object]] | None = None,
) -> tuple[str, Callable[[], None], ActiveSceneNamespace]:
    """Boot *hw* into its boot scene; return its name, per-tick body and namespace.

    The one boot shared by the device (:func:`app.scene_runtime.run_scene`)
    and the Simulated device, as :func:`build_scene_tick` is their one tick.
    The card's persisted ``scene`` wins over *settings_mapping*'s
    ``default_scene``; an unknown name raises naming the known scenes. A
    reboot the scene asks for persists to ``hw.storage``, then calls *reset*.

    *scene_data* maps a scene name to tunables merged over its
    ``initial_data``; the Simulated device boots shortened scenes through it.

    The namespace is the runtime's own Active scene namespace, so the
    Simulated device can resolve a clip name exactly as the game does.
    """
    catalog = scan_boot_pack_catalog(hw.storage, scene_data)
    scene_registry = catalog.scene_registry
    scene_name = resolve_boot_scene_name(scene_registry, hw.storage, settings_mapping, logger)
    if hw.ir is not None:
        hw.ir.apply_codec(*resolve_ir_codec(scene_registry, scene_name))
    scene_reboot = DeviceSceneReboot(
        hw.storage, booted_scene=scene_name, reset=reset, logger=logger
    )
    runtime = build_scene_runtime(hw, scene_name, catalog, scene_reboot=scene_reboot, timer=timer)
    return scene_name, build_scene_tick(hw, runtime), runtime.namespace


def build_scene_tick(hw: DeviceHardware, runtime: SceneRuntime) -> Callable[[], None]:
    """Return the per-tick body that drives *runtime* on *hw*; call it once per tick.

    The one loop body shared by the device
    (:func:`app.scene_runtime.run_scene`, which adds only ``while True:`` and
    ``gc.collect()``) and the Simulated device, so neither copies it, as
    both share the boot that builds it (:func:`build_scene_boot`). Build it
    once per runtime: the ``InputEvents.Sensors`` event, its button buffer,
    and the telemetry gate are allocated here (the acceleration and magnetic
    buffers are each sensor's own
    :class:`~hardware.shared.polled_sensor.PolledSensor` ``reading``)
    and mutated in place every tick, so the steady-state tick allocates
    nothing on-device.

    A caller with events of its own to inject queues them on
    ``runtime.manager.active_state`` before calling the tick; they are
    dispatched in that tick's ``manager.update()``.
    """
    accelerometer = hw.accelerometer
    magnetometer = hw.magnetometer
    button_data = ButtonData({})
    acceleration = accelerometer.reading if accelerometer is not None else None
    magnetic = magnetometer.reading if magnetometer is not None else None
    # Narrow each PolledSensor.reading, typed as either buffer, to the one it holds.
    assert acceleration is None or isinstance(acceleration, AccelerationData)
    assert magnetic is None or isinstance(magnetic, MagneticData)
    input_event = InputEvents.Sensors(button_data, acceleration, magnetic)
    manager = runtime.manager
    effect_manager = runtime.effect_manager
    timer = runtime.timer
    ir = runtime.ir
    radio = runtime.radio
    last_telemetry_print_total = 0.0

    def tick() -> None:
        nonlocal last_telemetry_print_total

        hw.buttons.update(timer.elapsed, button_data)

        if accelerometer is not None:
            accelerometer.update()

        if magnetometer is not None:
            magnetometer.update()

        # Unconditional, before the active_state check: a send can be in
        # flight across a scene transition, and ir.update() always pumps so
        # a deferred end_transmit still arms the flush latch its own receive
        # consumes this same tick. It also always receives when a receiver
        # is wired, so a packet decoded while no scene is active is
        # drained-and-dropped here rather than left to overflow — only the
        # queuing below is conditional on a scene being active. A no-op
        # when no ir section is wired at all (ir is None).
        if ir is not None:
            ir.update()

        # Same unconditional rationale as ir.update() above: radio.update()
        # always polls for a waiting packet regardless of whether a scene is
        # active, so a packet decoded with no active scene is simply never
        # queued below rather than left to build up in the transport. A
        # no-op when no radio peripheral is wired at all (radio is None).
        if radio is not None:
            radio.update()

        active_state = manager.active_state

        if active_state is not None:
            if ir is not None and ir.received is not None:
                active_state.queue_event(
                    NetworkEvents.IRReceived(
                        ir.received,
                        ir.last_signal_strength,
                        ir.last_error_margin,
                        best_receiver=None,
                    )
                )
            if radio is not None and radio.received is not None:
                active_state.queue_event(
                    NetworkEvents.RadioReceived(radio.received, str(radio.last_sender))
                )
            active_state.queue_event(input_event)
        manager.update()
        effect_manager.update(timer)

        if timer.total - last_telemetry_print_total >= _TELEMETRY_PRINT_INTERVAL:
            last_telemetry_print_total = timer.total
            line = ir.telemetry_line() if ir is not None else None
            if line is not None:
                print(line)

    return tick
