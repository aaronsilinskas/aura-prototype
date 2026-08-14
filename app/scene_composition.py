"""Board-free scene wiring — builds the engine/effect/scene machinery for one scene.

CPython-testable: imports only engine, ``hardware.shared.scene_selection``, and
the board-free ``DeviceHardware`` type. No ``TYPE_CHECKING`` guard is needed
because ``DeviceHardware`` itself carries no board imports.
"""

from __future__ import annotations

import engine._path as _path
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_manager import InfraredManager
from hardware.shared.radio_manager import RadioManager

__all__ = ["SceneRuntime", "build_scene_runtime"]


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


def _scan_effect_pack_sounds(audio_registry: AudioRegistry, pack_names: list[str]) -> None:
    """Scan each named effect pack's ``sounds`` folder into *audio_registry*'s base.

    *pack_names* is the already-scanned effect-pack list (``effect_registry.names()``)
    so this reuses the pack-detection *build_scene_runtime* already did instead of
    re-walking ``packs/effects``. A pack with no ``sounds/`` folder scans to an
    empty merge — ``AudioRegistry.scan_pack_sounds`` tolerates a missing directory.
    """
    for pack_name in pack_names:
        sounds_dir = _path.join(_path.join(_EFFECT_PACKS_DIR, pack_name), "sounds")
        audio_registry.scan_pack_sounds(pack_name, sounds_dir)


def _resolve_known_scene(scene_registry: SceneRegistry, scene_name: str) -> str:
    """Return *scene_name* if registered, else raise naming the known scenes."""
    names = scene_registry.names()
    if scene_name in names:
        return scene_name
    raise ValueError(f"unknown scene {scene_name!r}; known scenes: {', '.join(names)}")


def build_scene_runtime(hw: DeviceHardware, scene_name: str) -> SceneRuntime:
    """Wire up the effect/rule/scene registries and load *scene_name*.

    Raises ``ValueError`` naming the known scenes when *scene_name* is not in
    the scanned scene registry. The returned ``SceneRuntime`` has the resolved
    scene already active — the caller only needs to drive the per-tick loop.
    """
    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")

    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)

    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        network_controls=hw.network_controls,
        timer=timer,
    )

    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    # hw.audio_registry is the same AudioRegistry the device's AudioEffectOutput
    # resolves clips through — scanning effect-pack sounds into its base and
    # installing it as SceneManager's audio-overlay admin here is what lets
    # scene./<pack>.-prefixed clip names resolve at runtime. A device with no
    # enabled audio section has nothing to scan or wire into; a fresh,
    # unreachable AudioRegistry keeps SceneManager's non-optional seam satisfied
    # without pretending sound resolution works.
    audio_registry = hw.audio_registry
    if audio_registry is not None:
        _scan_effect_pack_sounds(audio_registry, effect_registry.names())
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
    manager.load(_resolve_known_scene(scene_registry, scene_name))
    manager.update()  # applies the load transition; the scene is now active

    ir = InfraredManager(hw.transmit_pump, hw.ir_receiver)
    radio = RadioManager(hw.radio)

    return SceneRuntime(
        manager=manager, effect_manager=effect_manager, timer=timer, ir=ir, radio=radio
    )
