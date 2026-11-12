"""The Scene boot: ``build_scene_boot`` turns a device's hardware into a booted scene and its tick.

Its interface is ``build_scene_boot`` and the ``SceneBoot`` it returns; every
boot step below is private. CPython-testable: imports only ``engine`` and the
board-free modules under ``hardware.shared``, so no ``TYPE_CHECKING`` guard
is needed.
"""

from __future__ import annotations

import engine._path as _path
from engine.capabilities import MissingCapabilityError, describe_capabilities
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, InputEvents, MagneticData
from engine.log import Logger
from engine.namespace import ActiveSceneNamespace
from engine.network import NetworkEvents
from engine.pack_catalog import PackCatalog, SettingOverrides, scan_pack_roots
from engine.scene import SceneManager, SceneRegistry
from engine.state import SceneControls, SceneReboot
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs import codec_for
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.scene_selection import apply_scene_deploy, boot_scene_candidates

try:
    from collections.abc import Callable
except ImportError:
    pass  # collections.abc not available on all embedded runtimes

__all__ = ["SceneBoot", "build_scene_boot"]


class _SceneRuntime:
    """Bundle of the live objects a scene's per-tick loop drives.

    ``manager`` applies scene transitions, ``effect_manager`` renders the
    active scene's effects, and ``timer`` tracks elapsed/total tick time.
    ``namespace`` is the Active scene namespace ``manager`` installs each
    scene into and ``effect_manager`` resolves names through.
    """

    __slots__ = ("effect_manager", "manager", "namespace", "timer")

    def __init__(
        self,
        manager: SceneManager,
        effect_manager: EffectManager,
        timer: Timer,
        namespace: ActiveSceneNamespace,
    ) -> None:
        self.manager: SceneManager = manager
        self.effect_manager: EffectManager = effect_manager
        self.timer: Timer = timer
        self.namespace: ActiveSceneNamespace = namespace


class SceneBoot:
    """What ``build_scene_boot`` hands back: the booted scene and how to drive it.

    ``scene_name`` is the scene the device booted into and ``tick`` the
    per-tick body to call once per tick. ``scene_controls`` are the booted
    scene's ``SceneControls``, the same ones its rules hold: they cover it
    with an Overlay, pop it, or reboot. ``namespace`` is the game's own
    Active scene namespace, so a caller resolves a clip name exactly as the
    running game does.
    """

    __slots__ = ("namespace", "scene_controls", "scene_name", "tick")

    def __init__(
        self,
        scene_name: str,
        tick: Callable[[], None],
        scene_controls: SceneControls,
        namespace: ActiveSceneNamespace,
    ) -> None:
        self.scene_name: str = scene_name
        self.tick: Callable[[], None] = tick
        self.scene_controls: SceneControls = scene_controls
        self.namespace: ActiveSceneNamespace = namespace


_TELEMETRY_PRINT_INTERVAL = 1.0  # seconds
_FLASH_PACKS_ROOT = "packs"
_CARD_PACKS_ROOT = "aura_packs"


def _resolve_boot_scene_name(
    scene_registry: SceneRegistry,
    storage: DeviceStorage | None,
    boot_mapping: dict,
    capabilities: frozenset[str],
    logger: Logger | None = None,
) -> str:
    """Return the registered boot scene whose Required capabilities are all in *capabilities*.

    Tries the card's Persisted scene, then flash ``default_scene`` (see
    ``boot_scene_candidates``); a ``None`` *storage* has no Persisted scene.
    A candidate unknown to *scene_registry* raises ``ValueError`` naming the
    known scenes. A Persisted scene the device can't run is skipped and
    logged once to *logger*, and left on the card.

    Raises:
        MissingCapabilityError: No candidate fits; names the last one tried
            and what it is missing.
    """
    logger = logger if logger is not None else Logger.SILENT
    persisted, fallback = boot_scene_candidates(storage, boot_mapping, logger)
    if persisted is not None:
        scene_name = scene_registry.resolve_known(persisted)
        missing = scene_registry.missing_capabilities(scene_name, capabilities)
        if not missing:
            return scene_name
        logger.log(
            f"skipping Persisted scene {scene_name!r}: the device lacks "
            + describe_capabilities(missing)
        )
    scene_name = scene_registry.resolve_known(fallback)
    missing = scene_registry.missing_capabilities(scene_name, capabilities)
    if missing:
        raise MissingCapabilityError(missing, scene_name)
    return scene_name


def _resolve_ir_codec(
    scene_registry: SceneRegistry, scene_name: str
) -> tuple[type[InfraredEncoder], type[InfraredDecoder]]:
    """Return the encoder/decoder class pair of the wire-frame codec *scene_name* declares.

    Defaults to the ``"aura"`` codec when the scene declares none, and needs
    no built hardware to resolve.
    """
    return codec_for(scene_registry.ir_codec_for(scene_name))


def _scan_boot_pack_catalog(
    storage: DeviceStorage | None,
    setting_overrides: SettingOverrides | None = None,
) -> PackCatalog:
    """Scan the device's pack roots into the one ``PackCatalog`` boot runs on.

    Flash ``packs`` always; the card's ``aura_packs`` only when *storage* is
    mounted and carries that folder. Call it after storage mounts.
    *setting_overrides* is passed through as the catalog's Setting overrides
    (see ``scan_pack_roots``).

    Raises:
        PackScanError: a pack or scene under either root is misconfigured.
    """
    roots = [_FLASH_PACKS_ROOT]
    if storage is not None:
        card_root = storage.path(_CARD_PACKS_ROOT)
        if _path.isdir(card_root):
            roots.append(card_root)
    return scan_pack_roots(roots, setting_overrides=setting_overrides)


def _build_scene_runtime(
    hw: DeviceHardware,
    scene_name: str,
    catalog: PackCatalog,
    scene_reboot: SceneReboot | None = None,
    timer: Timer | None = None,
) -> _SceneRuntime:
    """Wire the engine to *catalog*'s registries and boot into *scene_name* from it.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    the catalog's ``SceneRegistry``. The returned ``_SceneRuntime`` has the
    resolved scene already active — the caller only needs to drive the
    per-tick loop.

    *catalog* is the one boot scan from ``_scan_boot_pack_catalog``, shared
    with boot-scene and IR-codec resolution; nothing is scanned here.

    *scene_reboot*, if supplied, is the board-free ``SceneReboot`` port wired
    into ``SceneManager`` so rules can call ``state.scene_controls.reboot_into``/
    ``reboot_to_previous``. This function stays board-free, so it never
    constructs the live adapter itself -- ``build_scene_boot`` supplies it
    (see ``hardware.shared.device_reboot``). Omitted, a fresh base
    ``SceneReboot`` stands in, satisfying ``SceneManager``'s non-optional seam
    without pretending a reboot request can go anywhere.

    *timer*, if supplied, is the clock the whole runtime ticks on — the
    engine, the effects, and the Polled parts the tick updates. The
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
        capabilities=hw.capabilities,
    )

    manager = SceneManager(
        engine,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        scene_reboot=scene_reboot if scene_reboot is not None else SceneReboot(),
    )
    manager.activate_boot_scene(scene_registry.resolve_known(scene_name))

    return _SceneRuntime(
        manager=manager,
        effect_manager=effect_manager,
        timer=timer,
        namespace=namespace,
    )


def build_scene_boot(
    hw: DeviceHardware,
    boot_mapping: dict,
    reset: Callable[[], None],
    timer: Timer | None = None,
    logger: Logger | None = None,
    setting_overrides: SettingOverrides | None = None,
) -> SceneBoot:
    """Boot *hw* into its boot scene; return the ``SceneBoot`` that names and drives it.

    The one boot shared by the device (:func:`app.scene_runtime.run_scene`)
    and the Simulated device, whose returned tick is also their one loop body.
    A pending Scene deploy token is applied first (see
    :func:`~hardware.shared.scene_selection.apply_scene_deploy`); then the
    card's Persisted scene wins over *boot_mapping*'s ``default_scene``. A
    reboot the scene asks for persists to ``hw.storage``, then calls *reset*.

    *setting_overrides* overrides scenes' Settings (shaped as for
    ``scan_pack_roots``); the Simulated device boots shortened scenes through
    it.

    Raises:
        PackScanError: a pack or scene under a scanned pack root is
            misconfigured.
        MissingCapabilityError: no boot scene candidate fits the device's
            Capabilities.
        ValueError: neither boot file names a scene, a named scene is
            unknown (the message names the known scenes), or the booted
            scene declares an unknown wire-frame codec.
    """
    catalog = _scan_boot_pack_catalog(hw.storage, setting_overrides)
    scene_registry = catalog.scene_registry
    apply_scene_deploy(hw.storage, boot_mapping, logger)
    scene_name = _resolve_boot_scene_name(
        scene_registry, hw.storage, boot_mapping, hw.capabilities, logger
    )
    if hw.ir is not None:
        hw.ir.apply_codec(*_resolve_ir_codec(scene_registry, scene_name))
    scene_reboot = DeviceSceneReboot(
        hw.storage, booted_scene=scene_name, reset=reset, logger=logger
    )
    runtime = _build_scene_runtime(hw, scene_name, catalog, scene_reboot=scene_reboot, timer=timer)
    return SceneBoot(scene_name, _build_scene_tick(hw, runtime), runtime.manager, runtime.namespace)


def _build_scene_tick(hw: DeviceHardware, runtime: _SceneRuntime) -> Callable[[], None]:
    """Return the per-tick body that drives *runtime* on *hw*; call it once per tick.

    The one loop body shared by the device
    (:func:`app.scene_runtime.run_scene`, which adds only ``while True:`` and
    ``gc.collect()``) and the Simulated device, so neither copies it, as
    both share the boot that builds it (:func:`build_scene_boot`). Each tick
    updates every Polled part in ``hw.polled``, naming none, then builds
    the events from their state. Build it once per runtime: the
    ``InputEvents.Sensors`` event and the telemetry gate are allocated here
    (the button, acceleration and magnetic buffers are each part's own
    ``reading``) and mutated in place every tick, so the steady-state tick
    allocates nothing on-device.
    """
    polled = hw.polled
    accelerometer = hw.accelerometer
    magnetometer = hw.magnetometer
    button_data = hw.buttons.reading
    acceleration = accelerometer.reading if accelerometer is not None else None
    magnetic = magnetometer.reading if magnetometer is not None else None
    # Narrow each PolledSensor.reading, typed as either buffer, to the one it holds.
    assert acceleration is None or isinstance(acceleration, AccelerationData)
    assert magnetic is None or isinstance(magnetic, MagneticData)
    input_event = InputEvents.Sensors(button_data, acceleration, magnetic)
    manager = runtime.manager
    effect_manager = runtime.effect_manager
    timer = runtime.timer
    ir = hw.ir
    radio = hw.radio
    last_telemetry_print_total = 0.0

    def tick() -> None:
        nonlocal last_telemetry_print_total

        elapsed = timer.elapsed
        # Polled before the active_state check, so a send in flight across a
        # scene transition still completes and a packet received with no scene
        # active is drained and dropped rather than left to overflow; only the
        # queuing below waits on a scene.
        for part in polled:
            part.update(elapsed)

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
