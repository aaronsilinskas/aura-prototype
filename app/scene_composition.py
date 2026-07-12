"""Board-free scene wiring — builds the engine/effect/scene machinery for one scene.

CPython-testable: imports only engine, ``hardware.shared.scene_selection``, and
the board-free ``DeviceHardware`` type. No ``TYPE_CHECKING`` guard is needed
because ``DeviceHardware`` itself carries no board imports.
"""

from __future__ import annotations

from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_manager import InfraredManager

__all__ = ["SceneRuntime", "build_scene_runtime"]


class SceneRuntime:
    """Bundle of the live objects a scene's per-tick loop drives.

    ``manager`` applies scene transitions, ``effect_manager`` renders the
    active scene's effects, ``timer`` tracks elapsed/total tick time, and
    ``ir`` owns the per-tick pump-before-receive IR sequence.
    """

    __slots__ = ("effect_manager", "ir", "manager", "timer")

    def __init__(
        self,
        manager: SceneManager,
        effect_manager: EffectManager,
        timer: Timer,
        ir: InfraredManager,
    ) -> None:
        self.manager: SceneManager = manager
        self.effect_manager: EffectManager = effect_manager
        self.timer: Timer = timer
        self.ir: InfraredManager = ir


def _resolve_known_scene(scene_registry: SceneRegistry, scene_name: str) -> str:
    """Return *scene_name* if registered, else raise naming the known scenes."""
    names = scene_registry.names()
    if scene_name in names:
        return scene_name
    raise ValueError("unknown scene '" + scene_name + "'; known scenes: " + ", ".join(names))


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

    manager = SceneManager(
        engine, effect_registry, rule_registry, scene_registry, effect_admin=effect_manager
    )
    manager.load(_resolve_known_scene(scene_registry, scene_name))
    manager.update()  # applies the load transition; the scene is now active

    ir = InfraredManager(hw.transmit_pump, hw.ir_receiver)

    return SceneRuntime(manager=manager, effect_manager=effect_manager, timer=timer, ir=ir)
