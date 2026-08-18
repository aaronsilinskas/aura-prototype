"""Board-free scene wiring — builds the engine/effect/scene machinery for one scene.

CPython-testable: imports only ``engine`` and the board-free modules under
``hardware.shared`` (``device_hardware``, ``ir_codecs``, ``ir_manager``,
``radio_manager``). No ``TYPE_CHECKING`` guard is needed because none of them
carry board imports.
"""

from __future__ import annotations

import sys

import engine._path as _path
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_storage import DeviceStorage
from hardware.shared.ir_codecs import codec_for
from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder
from hardware.shared.ir_manager import InfraredManager
from hardware.shared.radio_manager import RadioManager

__all__ = ["SceneRuntime", "build_scene_runtime", "resolve_ir_codec", "resolve_known_scene"]


class SceneRuntime:
    """Bundle of the live objects a scene's per-tick loop drives.

    ``manager`` applies scene transitions, ``effect_manager`` renders the
    active scene's effects, ``timer`` tracks elapsed/total tick time, ``ir``
    owns the per-tick pump-before-receive IR sequence, and ``radio`` owns the
    per-tick radio receive poll.
    """

    __slots__ = ("effect_manager", "ir", "manager", "radio", "timer")

    def __init__(
        self,
        manager: SceneManager,
        effect_manager: EffectManager,
        timer: Timer,
        ir: InfraredManager,
        radio: RadioManager,
    ) -> None:
        self.manager: SceneManager = manager
        self.effect_manager: EffectManager = effect_manager
        self.timer: Timer = timer
        self.ir: InfraredManager = ir
        self.radio: RadioManager = radio


_EFFECT_PACKS_DIR = "packs/effects"
_CARD_PACKS_DIR = "aura_packs"
_CARD_SCENES_MODULE_PREFIX = "aura_packs.scenes"
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
    names = scene_registry.names()
    if scene_name in names:
        return scene_name
    raise ValueError(f"unknown scene {scene_name!r}; known scenes: {', '.join(names)}")


def resolve_ir_codec(
    scene_registry: SceneRegistry, scene_name: str
) -> tuple[InfraredEncoder, InfraredDecoder]:
    """Return the instantiated wire-frame codec *scene_name* declares.

    Reads the scene's declared codec name via ``SceneRegistry.ir_codec_for``
    (``"aura"`` when the scene declares none) and maps it to a class pair via
    ``ir_codecs.codec_for``, then constructs one instance of each -- board-free,
    so this can run ahead of ``build_hardware`` and feed its ``ir_encoder`` /
    ``ir_decoder`` seam directly.
    """
    codec_name = scene_registry.ir_codec_for(scene_name)
    encoder_cls, decoder_cls = codec_for(codec_name)
    return encoder_cls(), decoder_cls()


def _ensure_card_on_sys_path(storage: DeviceStorage) -> bool:
    """Return whether the mounted card carries a top-level ``aura_packs/`` directory.

    When it does, *storage*'s ``mount_root`` is appended to ``sys.path``
    (guarded so a repeat ``build_scene_runtime`` call never duplicates the
    entry), which is what lets any ``aura_packs.`` package on the card --
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


def _scan_card_scenes(scene_registry: SceneRegistry, storage: DeviceStorage | None) -> None:
    """Scan the card's ``aura_packs/scenes`` into *scene_registry*, if present.

    A no-op when *storage* is ``None`` or the mounted card carries no
    top-level ``aura_packs/`` directory -- card scenes are purely additive on
    top of flash discovery (see ``_ensure_card_on_sys_path``). The absolute
    ``aura_packs/scenes`` path -- resolved through the ``DeviceStorage`` port
    via ``storage.path``, never a re-derived ``"/sd"`` literal, preserving its
    no-escape rule -- is scanned into *scene_registry* under the module prefix
    ``"aura_packs.scenes"``, the same registry flash scenes live in, so a
    scene name present on both sides raises via ``SceneRegistry.scan_dir``'s
    cross-root collision check. Missing entirely (``aura_packs/`` with no
    ``scenes/`` subdirectory), the scan is skipped rather than raising --
    ``SceneRegistry.scan_dir`` has no directory-existence guard of its own.
    """
    if storage is None:
        return
    if not _ensure_card_on_sys_path(storage):
        return

    card_scenes_path = storage.path(_path.join(_CARD_PACKS_DIR, "scenes"))
    if not _path.isdir(card_scenes_path):
        return

    scene_registry.scan_dir(card_scenes_path, _CARD_SCENES_MODULE_PREFIX)


def _scan_card_effects(effect_registry: PackRegistry, storage: DeviceStorage | None) -> str | None:
    """Scan the card's ``aura_packs/effects`` into *effect_registry*, if present.

    Mirrors ``_scan_card_scenes`` -- same ``storage is None`` / no top-level
    ``aura_packs/`` no-op, same ``sys.path`` gating via
    ``_ensure_card_on_sys_path`` -- but scans into the *same* effect
    ``PackRegistry`` flash's ``packs/effects`` populates, under the distinct
    module prefix ``"aura_packs.effects"``, rather than a ``SceneRegistry``.
    A pack name present on both sides raises via ``PackRegistry.scan_dir``'s
    existing cross-root collision check -- overriding a flash pack from the
    card is out of scope, not silently allowed.

    Returns the absolute on-card effects-root path when a scan happened, so
    ``build_scene_runtime`` can add it to the roots ``_scan_effect_pack_sounds``
    walks without re-deriving or re-probing the same path; returns ``None`` in
    every no-op case (no storage, no ``aura_packs/``, or ``aura_packs/`` with
    no ``effects/`` subdirectory).
    """
    if storage is None:
        return None
    if not _ensure_card_on_sys_path(storage):
        return None

    card_effects_path = storage.path(_path.join(_CARD_PACKS_DIR, "effects"))
    if not _path.isdir(card_effects_path):
        return None

    effect_registry.scan_dir(card_effects_path, _CARD_EFFECTS_MODULE_PREFIX)
    return card_effects_path


def build_scene_runtime(
    hw: DeviceHardware, scene_name: str, scene_registry: SceneRegistry | None = None
) -> SceneRuntime:
    """Wire up the effect/rule/scene registries and load *scene_name*.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    the scanned scene registry. The returned ``SceneRuntime`` has the resolved
    scene already active — the caller only needs to drive the per-tick loop.

    *scene_registry*, if supplied, is used as-is instead of scanning a fresh
    one -- the seam ``run_scene`` uses to share the one registry scan it did
    to resolve the boot-time IR codec (see ``resolve_ir_codec``) with the
    scene load here, so an unknown scene name is discovered once, before
    hardware is built, rather than scanned and validated twice. Omitted, a
    fresh registry is scanned here so existing callers keep working unchanged.

    After flash scenes are scanned (or the supplied registry is accepted
    as-is), ``hw.storage``'s ``aura_packs/scenes`` is scanned into the same
    registry via ``_scan_card_scenes`` -- a no-op with no storage or no
    ``aura_packs/`` on the card, so a device with neither behaves exactly as
    before. Likewise, after flash effect packs are scanned, ``hw.storage``'s
    ``aura_packs/effects`` is scanned into the same effect ``PackRegistry``
    via ``_scan_card_effects``, so a card effect pack resolves through
    ``effect_manager`` exactly like a flash one.
    """
    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    card_effects_root = _scan_card_effects(effect_registry, hw.storage)

    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)

    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        network_controls=hw.network_controls,
        timer=timer,
    )

    if scene_registry is None:
        scene_registry = SceneRegistry()
        scene_registry.scan_dir("packs/scenes", "packs.scenes")

    _scan_card_scenes(scene_registry, hw.storage)

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
    )
    manager.load(resolve_known_scene(scene_registry, scene_name))
    manager.update()  # applies the load transition; the scene is now active

    ir = InfraredManager(hw.transmit_pump, hw.ir_receiver)
    radio = RadioManager(hw.radio)

    return SceneRuntime(
        manager=manager, effect_manager=effect_manager, timer=timer, ir=ir, radio=radio
    )
