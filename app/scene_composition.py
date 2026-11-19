"""The Scene boot: ``build_scene_boot`` turns a device's hardware into a booted scene and its tick.

Its interface is ``build_scene_boot`` and the ``SceneBoot`` it returns; every
boot step below is private. It runs under CPython as well as on the device.
"""

from __future__ import annotations

import engine._path as _path
from engine.capabilities import MissingCapabilityError, describe_capabilities
from engine.input import InputEvents
from engine.log import Logger
from engine.namespace import ActiveSceneNamespace
from engine.network import NetworkEvents
from engine.pack_catalog import PackCatalog, SettingOverrides, scan_pack_roots
from engine.scene import SceneRegistry
from engine.scene_runtime import SceneRuntime
from engine.state import SceneControls, SceneReboot
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_reboot import DeviceSceneReboot
from hardware.shared.device_state import DeviceStateStore
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs import codec_for
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.persisted_scene import PersistedScene

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["SceneBoot", "build_scene_boot"]


class SceneBoot:
    """What ``build_scene_boot`` hands back: the booted scene and how to drive it.

    ``scene_name`` is the scene the device booted into and ``tick`` the
    per-tick body to call once per tick. ``scene_controls`` are the booted
    scene's ``SceneControls``, the same ones its rules hold: they cover it
    with an Overlay, pop it, or reboot. ``namespace`` is the game's own
    Active scene namespace, so a caller resolves a clip name exactly as the
    running game does. ``device_state`` is the boot's one ``DeviceStateStore``
    and ``persisted_scene`` the card's Persisted scene record over it, so a
    caller reads the card without opening a second store.
    """

    __slots__ = (
        "device_state",
        "namespace",
        "persisted_scene",
        "scene_controls",
        "scene_name",
        "tick",
    )

    def __init__(
        self,
        scene_name: str,
        tick: Callable[[], None],
        scene_controls: SceneControls,
        namespace: ActiveSceneNamespace,
        device_state: DeviceStateStore,
        persisted_scene: PersistedScene,
    ) -> None:
        self.scene_name: str = scene_name
        self.tick: Callable[[], None] = tick
        self.scene_controls: SceneControls = scene_controls
        self.namespace: ActiveSceneNamespace = namespace
        self.device_state: DeviceStateStore = device_state
        self.persisted_scene: PersistedScene = persisted_scene


_TELEMETRY_PRINT_INTERVAL = 1.0  # seconds
_FLASH_PACKS_ROOT = "packs"
_CARD_PACKS_ROOT = "aura_packs"


def _resolve_boot_scene_name(
    scene_registry: SceneRegistry,
    persisted_scene: PersistedScene,
    boot_mapping: dict,
    capabilities: frozenset[str],
    logger: Logger | None = None,
) -> str:
    """Return the registered boot scene whose Required capabilities are all in *capabilities*.

    Tries the card's Persisted scene, then flash ``default_scene`` (see
    ``PersistedScene.boot_candidates``).
    A Persisted scene unknown to *scene_registry*, or one the device can't
    run, is skipped, logged once to *logger*, and left on the card: the card
    may go back to a prop that has it and can run it. With no flash
    ``default_scene`` the Persisted scene is the fallback, with nothing to
    skip to, so it is never skipped.

    Raises:
        ValueError: The fallback is unknown to *scene_registry*; names the
            known scenes.
        MissingCapabilityError: No candidate fits; names the last one tried
            and what it is missing.
    """
    logger = logger if logger is not None else Logger.SILENT
    persisted, fallback = persisted_scene.boot_candidates(boot_mapping)
    if persisted is not None:
        if persisted not in scene_registry.names():
            logger.log(f"skipping Persisted scene {persisted!r}: unknown scene on this device")
        else:
            missing = scene_registry.missing_capabilities(persisted, capabilities)
            if not missing:
                return persisted
            logger.log(
                f"skipping Persisted scene {persisted!r}: the device lacks "
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
    scene_reboot: SceneReboot,
    timer: Timer | None,
    logger: Logger | None,
) -> SceneRuntime:
    """Build the ``SceneRuntime`` on *hw* from *catalog* and boot it into *scene_name*.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    the catalog's ``SceneRegistry``. *catalog* is the one boot scan from
    ``_scan_boot_pack_catalog``, shared with boot-scene and IR-codec
    resolution; nothing is scanned here. *timer* is the clock the scene, its
    effects and the Polled parts the tick updates all run on; ``None`` lets
    the runtime build a wall clock. *logger* is where the runtime logs a
    declined Return to lobby.
    """
    runtime = SceneRuntime(
        catalog,
        hw.outputs,
        hw.network_controls,
        hw.capabilities,
        scene_reboot,
        clock=timer,
        logger=logger,
    )
    runtime.activate_boot_scene(catalog.scene_registry.resolve_known(scene_name))
    return runtime


def build_scene_boot(
    hw: DeviceHardware,
    boot_mapping: dict,
    reset: Callable[[], None],
    timer: Timer | None = None,
    logger: Logger | None = None,
    setting_overrides: SettingOverrides | None = None,
) -> SceneBoot:
    """Boot *hw* into its boot scene; return the ``SceneBoot`` that names and drives it.

    The one boot shared by the device (:func:`app.run_scene.run_scene`)
    and the Simulated device, whose returned tick is also their one loop body.
    A pending Scene deploy token is applied first (see
    :meth:`~hardware.shared.persisted_scene.PersistedScene.apply_scene_deploy`); then the
    card's Persisted scene wins over *boot_mapping*'s ``default_scene``,
    unless this device doesn't know it or can't run it: then it is skipped,
    logged to *logger* and left on the card. A reboot the scene asks for
    persists to ``hw.storage``, then calls *reset*. One ``DeviceStateStore``
    over ``hw.storage`` serves the whole boot.

    *setting_overrides* overrides scenes' Settings (shaped as for
    ``scan_pack_roots``); the Simulated device boots shortened scenes through
    it.

    Raises:
        PackScanError: a pack or scene under a scanned pack root is
            misconfigured.
        MissingCapabilityError: no boot scene candidate fits the device's
            Capabilities.
        ValueError: neither boot file names a scene; the flash
            ``default_scene`` is unknown, or there is none and the Persisted
            scene is unknown (the message names the known scenes); or the
            booted scene declares an unknown wire-frame codec.
    """
    catalog = _scan_boot_pack_catalog(hw.storage, setting_overrides)
    scene_registry = catalog.scene_registry
    device_state = DeviceStateStore(hw.storage, logger)
    persisted_scene = PersistedScene(device_state, logger)
    persisted_scene.apply_scene_deploy(boot_mapping)
    scene_name = _resolve_boot_scene_name(
        scene_registry, persisted_scene, boot_mapping, hw.capabilities, logger
    )
    if hw.ir is not None:
        hw.ir.apply_codec(*_resolve_ir_codec(scene_registry, scene_name))
    scene_reboot = DeviceSceneReboot(
        persisted_scene if hw.storage is not None else None,
        booted_scene=scene_name,
        reset=reset,
        logger=logger,
    )
    runtime = _build_scene_runtime(hw, scene_name, catalog, scene_reboot, timer, logger)
    tick = _build_scene_tick(hw, runtime)
    return SceneBoot(
        scene_name,
        tick,
        runtime.scene_controls,
        runtime.namespace,
        device_state,
        persisted_scene,
    )


def _build_scene_tick(hw: DeviceHardware, runtime: SceneRuntime) -> Callable[[], None]:
    """Return the per-tick body that drives *runtime* on *hw*; call it once per tick.

    Each tick advances the runtime's clock first, so the parts, rules and
    effects all see this tick's elapsed time. Build it once per runtime: the
    ``InputEvents.Sensors`` event and the telemetry gate are allocated here (the
    button, acceleration and magnetic buffers are each part's own ``reading``)
    and mutated in place every tick, so the steady-state tick allocates nothing
    on-device.
    """
    polled = hw.polled
    accelerometer = hw.accelerometer
    magnetometer = hw.magnetometer
    button_data = hw.buttons.reading
    acceleration = accelerometer.reading if accelerometer is not None else None
    magnetic = magnetometer.reading if magnetometer is not None else None
    input_event = InputEvents.Sensors(button_data, acceleration, magnetic)
    ir = hw.ir
    radio = hw.radio
    last_telemetry_print_total = 0.0

    def tick() -> None:
        nonlocal last_telemetry_print_total

        runtime.advance_clock()
        elapsed = runtime.elapsed
        # Polled whether or not a scene is active, so a send in flight across
        # a scene transition still completes; only building events waits on
        # a scene.
        for part in polled:
            part.update(elapsed)

        if runtime.has_active_scene:
            if ir is not None and ir.received is not None:
                runtime.queue_event(
                    NetworkEvents.IRReceived(
                        ir.received,
                        ir.last_signal_strength,
                        ir.last_error_margin,
                    )
                )
            if radio is not None and radio.received is not None:
                runtime.queue_event(
                    NetworkEvents.RadioReceived(radio.received, str(radio.last_sender))
                )
        runtime.queue_event(input_event)
        runtime.update()

        total = runtime.total
        if total - last_telemetry_print_total >= _TELEMETRY_PRINT_INTERVAL:
            last_telemetry_print_total = total
            line = ir.telemetry_line() if ir is not None else None
            if line is not None:
                print(line)

    return tick
