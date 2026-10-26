"""Board-free scene wiring — builds the engine/effect/scene machinery for one scene.

CPython-testable: imports only ``engine`` and the board-free modules under
``hardware.shared`` (``device_hardware``, ``ir_codecs``, ``ir_transceiver``,
``radio_transceiver``, ``scene_selection``). No ``TYPE_CHECKING`` guard is
needed because none of them carry board imports.
"""

from __future__ import annotations

import sys

import engine._path as _path
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.input import AccelerationData, ButtonData, InputEvents, MagneticData
from engine.log import Logger
from engine.network import NetworkEvents
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.state import SceneReboot
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
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
    "build_scene_runtime",
    "build_scene_tick",
    "resolve_boot_scene_name",
    "resolve_ir_codec",
    "resolve_known_scene",
    "scan_boot_scene_registry",
]


class SceneRuntime:
    """Bundle of the live objects a scene's per-tick loop drives.

    ``manager`` applies scene transitions, ``effect_manager`` renders the
    active scene's effects, ``timer`` tracks elapsed/total tick time, ``ir``
    is the device's ``InfraredTransceiver`` (``None`` on a device with no IR
    subsystem wired), and ``radio`` is the device's ``RadioTransceiver``
    (``None`` on a device with no radio peripheral wired) — both passed
    straight through from ``DeviceHardware``, no separate object built here.
    """

    __slots__ = ("effect_manager", "ir", "manager", "radio", "timer")

    def __init__(
        self,
        manager: SceneManager,
        effect_manager: EffectManager,
        timer: Timer,
        ir: InfraredTransceiver | None,
        radio: RadioTransceiver | None,
    ) -> None:
        self.manager: SceneManager = manager
        self.effect_manager: EffectManager = effect_manager
        self.timer: Timer = timer
        self.ir: InfraredTransceiver | None = ir
        self.radio: RadioTransceiver | None = radio


_TELEMETRY_PRINT_INTERVAL = 1.0  # seconds
_EFFECT_PACKS_DIR = "packs/effects"
_CARD_PACKS_DIR = "aura_packs"
_CARD_SCENES_MODULE_PREFIX = "aura_packs.scenes"
_CARD_RULES_MODULE_PREFIX = "aura_packs.rules"
_CARD_EFFECTS_MODULE_PREFIX = "aura_packs.effects"


def _scan_effect_pack_sounds(
    audio_registry: AudioRegistry, pack_names: list[str], effects_roots: list[str]
) -> None:
    """Scan each named effect pack's ``sounds`` folder into *audio_registry*'s base.

    *pack_names* is the already-scanned effect-pack list (``effect_registry.names()``)
    so this reuses the pack-detection *build_scene_runtime* already did instead of
    re-walking any effects directory. *effects_roots* is every effects root that
    was scanned into the registry -- flash's ``packs/effects`` plus, when the card
    carries one, its ``aura_packs/effects`` -- so a pack's ``sounds/`` is found
    regardless of which root it actually lives under. Trying a pack name against a
    root it doesn't live in is a harmless no-op: ``scan_pack_sounds`` tolerates a
    missing directory, and only the root that actually holds the pack contributes
    clips.
    """
    for pack_name in pack_names:
        for effects_root in effects_roots:
            sounds_dir = _path.join(_path.join(effects_root, pack_name), "sounds")
            audio_registry.scan_pack_sounds(pack_name, sounds_dir)


def resolve_known_scene(scene_registry: SceneRegistry, scene_name: str) -> str:
    """Return *scene_name* if registered, else raise naming the known scenes."""
    return scene_registry.resolve_known(scene_name)


def resolve_boot_scene_name(
    scene_registry: SceneRegistry,
    storage: DeviceStorage | None,
    settings_mapping: dict,
    logger: Logger | None = None,
) -> str:
    """Resolve the boot scene name and validate it against *scene_registry*.

    ``resolve_boot_scene`` decides only source precedence (persisted SD
    ``scene`` -> flash ``default_scene`` -> raise), never registry membership,
    so its result is validated here via ``resolve_known_scene`` -- an unknown
    name, from either source, raises naming the known scenes. A ``None``
    *storage* is treated as no persisted override, leaving the flash
    ``default_scene`` to win.
    """
    scene_name = resolve_boot_scene(storage, settings_mapping, logger)
    return resolve_known_scene(scene_registry, scene_name)


def resolve_ir_codec(
    scene_registry: SceneRegistry, scene_name: str
) -> tuple[InfraredEncoder, InfraredDecoder]:
    """Return the instantiated wire-frame codec *scene_name* declares.

    Defaults to the ``"aura"`` codec when the scene declares none, and needs
    no built hardware to resolve.
    """
    codec_name = scene_registry.ir_codec_for(scene_name)
    encoder_cls, decoder_cls = codec_for(codec_name)
    return encoder_cls(), decoder_cls()


def scan_boot_scene_registry(storage: DeviceStorage | None) -> SceneRegistry:
    """Build the complete boot-time scene registry: flash scenes, then card scenes.

    Constructs a fresh ``SceneRegistry``, scans flash ``packs/scenes`` into it,
    then scans *storage*'s ``aura_packs/scenes`` into the *same* registry via
    ``_scan_card_scenes`` -- the same discovery ``build_scene_runtime`` used to
    perform internally, now hoisted here so the complete registered-scene set
    exists before anything reads it (boot-scene resolution, IR-codec
    resolution, and scene-runtime construction all share this one registry).

    A card-less device (*storage* is ``None``) or a mounted card with no
    ``aura_packs/scenes`` both yield a flash-only registry, exactly as before
    this change. A card scene sharing a name with a flash scene raises the
    same cross-root collision error ``SceneRegistry.scan_dir`` already
    enforces.
    """
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")
    _scan_card_scenes(scene_registry, storage)
    return scene_registry


def _ensure_card_on_sys_path(storage: DeviceStorage) -> bool:
    """Return whether the mounted card carries a top-level ``aura_packs/`` directory.

    When it does, *storage*'s ``mount_root`` is appended to ``sys.path``
    (guarded so a repeat call against the same storage -- whether from
    ``scan_boot_scene_registry`` or ``build_scene_runtime`` -- never
    duplicates the entry), which is what lets any ``aura_packs.`` package on
    the card --
    scenes, effect packs, or their scene-local ``rules/``/``effects/`` --
    import against the card. Shared by every card-scan helper so the
    presence check and the ``sys.path`` mutation happen exactly once per
    kind of scan, from one source of truth.
    """
    card_packs_path = storage.path(_CARD_PACKS_DIR)
    if not _path.isdir(card_packs_path):
        return False

    mount_root = storage.mount_root
    if mount_root not in sys.path:
        sys.path.append(mount_root)
    return True


def _card_subdir_path(storage: DeviceStorage | None, subdir: str) -> str | None:
    """Return the card's absolute ``aura_packs/<subdir>`` path, if it exists.

    ``None`` when *storage* is ``None``, the mounted card carries no
    top-level ``aura_packs/`` directory, or ``aura_packs/`` has no *subdir*
    subdirectory. Otherwise ensures the card is on ``sys.path`` (via
    ``_ensure_card_on_sys_path``) and returns the absolute path -- resolved
    through the ``DeviceStorage`` port via ``storage.path``, never a
    re-derived ``"/sd"`` literal, preserving its no-escape rule. Shared by
    every card-scan helper so the presence checks read identically for
    scenes and effect packs alike.
    """
    if storage is None:
        return None
    if not _ensure_card_on_sys_path(storage):
        return None

    subdir_path = storage.path(_path.join(_CARD_PACKS_DIR, subdir))
    if not _path.isdir(subdir_path):
        return None

    return subdir_path


def _scan_card_scenes(scene_registry: SceneRegistry, storage: DeviceStorage | None) -> None:
    """Scan the card's ``aura_packs/scenes`` into *scene_registry*, if present.

    A no-op when ``_card_subdir_path`` finds no ``aura_packs/scenes`` --
    card scenes are purely additive on top of flash discovery. Otherwise the
    path is scanned into *scene_registry* under the module prefix
    ``"aura_packs.scenes"``, the same registry flash scenes live in, so a
    scene name present on both sides raises via ``SceneRegistry.scan_dir``'s
    cross-root collision check.
    """
    card_scenes_path = _card_subdir_path(storage, "scenes")
    if card_scenes_path is None:
        return

    scene_registry.scan_dir(card_scenes_path, _CARD_SCENES_MODULE_PREFIX)


def _scan_card_rules(rule_registry: PackRegistry, storage: DeviceStorage | None) -> None:
    """Scan the card's ``aura_packs/rules`` into *rule_registry*, if present.

    A no-op when ``_card_subdir_path`` finds no ``aura_packs/rules`` -- card
    rule packs are purely additive on top of flash discovery. Otherwise the
    path is scanned into *rule_registry* under the module prefix
    ``"aura_packs.rules"``, the same ``PackRegistry`` flash rule packs
    (``packs/rules``) live in, so a card rule pack is versioned exactly like a
    flash pack (``version.txt`` first line, a dir without one skipped) and a
    pack name present on both sides raises via ``PackRegistry.scan_dir``'s
    existing cross-root collision check. Rule packs carry no audio, so unlike
    ``_scan_effect_pack_sounds`` there is no sound wiring to do here.
    """
    card_rules_path = _card_subdir_path(storage, "rules")
    if card_rules_path is None:
        return

    rule_registry.scan_dir(card_rules_path, _CARD_RULES_MODULE_PREFIX)


def _scan_card_effects(effect_registry: PackRegistry, storage: DeviceStorage | None) -> str | None:
    """Scan the card's ``aura_packs/effects`` into *effect_registry*, if present.

    Mirrors ``_scan_card_scenes`` -- same no-op via ``_card_subdir_path`` --
    but scans into the *same* effect ``PackRegistry`` flash's
    ``packs/effects`` populates, under the distinct module prefix
    ``"aura_packs.effects"``, rather than a ``SceneRegistry``. A pack name
    present on both sides raises via ``PackRegistry.scan_dir``'s existing
    cross-root collision check -- overriding a flash pack from the card is
    out of scope, not silently allowed.

    Returns the absolute on-card effects-root path when a scan happened, so
    ``build_scene_runtime`` can add it to the roots ``_scan_effect_pack_sounds``
    walks without re-deriving or re-probing the same path; returns ``None`` in
    every no-op case (no storage, no ``aura_packs/``, or ``aura_packs/`` with
    no ``effects/`` subdirectory).
    """
    card_effects_path = _card_subdir_path(storage, "effects")
    if card_effects_path is None:
        return None

    effect_registry.scan_dir(card_effects_path, _CARD_EFFECTS_MODULE_PREFIX)
    return card_effects_path


def build_scene_runtime(
    hw: DeviceHardware,
    scene_name: str,
    scene_registry: SceneRegistry,
    scene_reboot: SceneReboot | None = None,
    timer: Timer | None = None,
) -> SceneRuntime:
    """Wire up the effect/rule registries and load *scene_name* from *scene_registry*.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    *scene_registry*. The returned ``SceneRuntime`` has the resolved scene
    already active — the caller only needs to drive the per-tick loop.

    *scene_registry* is a caller-supplied input, not discovered here: this
    function no longer scans scenes at all, neither the flash ``packs/scenes``
    self-scan nor ``hw.storage``'s ``aura_packs/scenes``. The caller builds it
    up front via ``scan_boot_scene_registry(hw.storage)`` -- the same complete
    registry boot-scene resolution and IR-codec resolution already consumed --
    and shares that one registry here, so a scene is scanned exactly once for
    the whole boot sequence.

    *scene_reboot*, if supplied, is the board-free ``SceneReboot`` port wired
    into ``SceneManager`` so rules can call ``state.scene_controls.reboot_into``/
    ``reboot_to_previous``. This function stays board-free, so it never
    constructs the live adapter itself -- device-only ``run_scene`` supplies
    it (see ``hardware.circuitpython.device_reboot``). Omitted, a fresh base
    ``SceneReboot`` stands in, satisfying ``SceneManager``'s non-optional seam
    without pretending a reboot request can go anywhere.

    *timer*, if supplied, is the clock the whole runtime ticks on — the
    engine, the effects, and the debouncer via ``SceneRuntime.timer``. The
    Simulation test harness passes a fixed-step clock here; omitted, a
    wall-clock ``Timer`` is built.

    ``hw.storage``'s ``aura_packs/rules`` is scanned into the rule registry
    via ``_scan_card_rules`` -- a no-op with no storage or no ``aura_packs/``
    on the card, so a device with neither behaves exactly as before.
    Likewise, after flash effect packs are scanned, ``hw.storage``'s
    ``aura_packs/effects`` is scanned into the same effect ``PackRegistry``
    via ``_scan_card_effects``, so a card effect pack resolves through
    ``effect_manager`` exactly like a flash one. Rule and effect registries
    stay build-internal -- unlike scenes, nothing outside this function reads
    them first.
    """
    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    card_effects_root = _scan_card_effects(effect_registry, hw.storage)

    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    _scan_card_rules(rule_registry, hw.storage)

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)

    if timer is None:
        timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        network_controls=hw.network_controls,
        timer=timer,
    )

    # hw.audio_registry is the same AudioRegistry the device's AudioEffectOutput
    # resolves clips through — scanning effect-pack sounds into its base and
    # installing it as SceneManager's audio-overlay admin here is what lets
    # scene./<pack>.-prefixed clip names resolve at runtime. A device with no
    # enabled audio section has nothing to scan or wire into; a fresh,
    # unreachable AudioRegistry keeps SceneManager's non-optional seam satisfied
    # without pretending sound resolution works.
    audio_registry = hw.audio_registry
    if audio_registry is not None:
        effects_roots = [_EFFECT_PACKS_DIR]
        if card_effects_root is not None:
            effects_roots.append(card_effects_root)
        _scan_effect_pack_sounds(audio_registry, effect_registry.names(), effects_roots)
    else:
        audio_registry = AudioRegistry()

    manager = SceneManager(
        engine,
        effect_registry,
        rule_registry,
        scene_registry,
        effect_admin=effect_manager,
        audio_overlay_admin=audio_registry,
        scene_reboot=scene_reboot if scene_reboot is not None else SceneReboot(),
    )
    manager.load(resolve_known_scene(scene_registry, scene_name))
    manager.update()  # applies the load transition; the scene is now active

    return SceneRuntime(
        manager=manager, effect_manager=effect_manager, timer=timer, ir=hw.ir, radio=hw.radio
    )


def build_scene_tick(hw: DeviceHardware, runtime: SceneRuntime) -> Callable[[], None]:
    """Return the per-tick body that drives *runtime* on *hw*; call it once per tick.

    The one loop body shared by the device
    (:func:`app.scene_runtime.run_scene`, which adds only ``while True:`` and
    ``gc.collect()``) and the Simulated device, so neither copies it. Build it
    once per runtime: the ``InputEvents.Sensors`` event, its
    button/acceleration/magnetic buffers, and the telemetry gate are
    allocated here and mutated in place every tick, so the steady-state tick
    allocates nothing on-device.

    A caller with events of its own to inject queues them on
    ``runtime.manager.active_state`` before calling the tick; they are
    dispatched in that tick's ``manager.update()``.
    """
    accelerometer = hw.accelerometer
    magnetometer = hw.magnetometer
    button_data = ButtonData({})
    acceleration = AccelerationData(0.0, 0.0, 0.0) if accelerometer is not None else None
    magnetic = MagneticData(0.0, 0.0, 0.0) if magnetometer is not None else None
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

        if acceleration is not None:
            try:
                ax, ay, az = accelerometer.acceleration
                acceleration.x = ax
                acceleration.y = ay
                acceleration.z = az
            except Exception:
                pass  # keep last good values; None signals missing hardware, not read failure

        if magnetic is not None:
            try:
                mx, my, mz = magnetometer.magnetic
                magnetic.x = mx
                magnetic.y = my
                magnetic.z = mz
            except Exception:
                pass  # keep last good values; None signals missing hardware, not read failure

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
