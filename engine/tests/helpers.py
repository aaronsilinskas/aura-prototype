from __future__ import annotations

from engine.effects.admin import EffectAdmin, HeldEffects, SceneView
from engine.effects.output import EffectOutput
from engine.engine import GameEngine
from engine.pack_catalog import PackCatalog
from engine.scene import SceneManager
from engine.scene_runtime import SceneRuntime
from engine.state import (
    EffectControls,
    EffectReceipt,
    GameState,
    NetworkControls,
    SceneReboot,
    ScopeValue,
)
from engine.timer import Timer

_STUB_RECEIPT_ID = 0


class SpyNetworkControls(NetworkControls):
    """Test spy that records send_ir and send_radio calls."""

    def __init__(self) -> None:
        self.send_ir_calls: list[tuple[bytes, str]] = []
        self.send_radio_calls: list[bytes] = []

    def send_ir(self, data: bytes, emitter: str) -> None:
        self.send_ir_calls.append((data, emitter))

    def send_radio(self, data: bytes) -> None:
        self.send_radio_calls.append(data)


class SpyEffectControls(EffectControls):
    """Test spy that records set_effect, stop_effect, and add_effect calls.

    ``add_effect`` stubs with a dummy ``EffectReceipt``. ``set_merge_strategy``
    is a defensive no-op: this spy is for rule unit tests, which may call it,
    but has no merge-strategy state of its own to record it against.
    """

    def __init__(self) -> None:
        self.set_effect_calls: list[tuple[ScopeValue, str, dict]] = []
        self.stop_effect_calls: list[ScopeValue] = []
        self.add_effect_calls: list[tuple[ScopeValue, str, dict]] = []

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        self.set_effect_calls.append((scope, name, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        self.add_effect_calls.append((scope, name, options))
        return EffectReceipt(_STUB_RECEIPT_ID)

    def stop_effect(self, scope: ScopeValue) -> None:
        self.stop_effect_calls.append(scope)

    def set_merge_strategy(self, scope: ScopeValue, strategy: object) -> None:
        pass  # no-op: SpyEffectControls has no merge-strategy state to record


class SpyEffectAdmin(EffectAdmin):
    """Test recorder for the scene-transition ``EffectAdmin`` face.

    ``steps`` records each step as ``(name, view)``, where *name* is
    ``"enter"``, ``"cover"`` or ``"uncover"``, so ``SceneManager`` transition
    tests can assert which step each transition took with which Scene view.
    ``cover`` returns a fresh, empty ``HeldEffects``, also kept in
    ``covered``; ``uncovered`` records the bundle each ``uncover`` was given.
    """

    def __init__(self) -> None:
        self.steps: list[tuple[str, SceneView]] = []
        self.covered: list[HeldEffects] = []
        self.uncovered: list[HeldEffects] = []

    def enter_boot_scene(self, view: SceneView) -> None:
        self.steps.append(("enter", view))

    def cover(self, view: SceneView) -> HeldEffects:
        self.steps.append(("cover", view))
        held = HeldEffects()
        self.covered.append(held)
        return held

    def uncover(self, held: HeldEffects, view: SceneView) -> None:
        self.steps.append(("uncover", view))
        self.uncovered.append(held)


class RecordingSceneReboot(SceneReboot):
    """Test recorder for the board-free ``SceneReboot`` port.

    Records every ``reboot_into``/``reboot_to_previous`` call instead of
    touching storage or resetting anything, so ``SceneManager``'s
    validate-then-delegate behaviour is testable without a live
    ``DeviceSceneReboot``. ``previous_scene`` answers *previous*.
    """

    def __init__(self, previous: str | None = None) -> None:
        self.reboot_into_calls: list[str] = []
        self.reboot_to_previous_calls: int = 0
        self._previous = previous

    def reboot_into(self, target: str) -> None:
        self.reboot_into_calls.append(target)

    def reboot_to_previous(self) -> None:
        self.reboot_to_previous_calls += 1

    def previous_scene(self) -> str | None:
        return self._previous


def active_state(manager: SceneManager) -> GameState:
    """The manager's active state, failing the test if no scene is loaded."""
    state = manager.active_state
    assert state is not None
    return state


class FrozenTimer(Timer):
    """A ``Timer`` that never advances, so a rule's timed behaviour stays put."""

    def update(self) -> None:
        pass


def rule_source(class_name: str = "ARule") -> str:
    """Return the source of a rule item whose ``RULE`` is an instance of a fresh *class_name*."""
    return (
        "from engine.engine import GameRule\n"
        "class " + class_name + "(GameRule): pass\n"
        "RULE = " + class_name + "()\n"
    )


def make_scene_manager(catalog: PackCatalog, effect_admin: SpyEffectAdmin) -> SceneManager:
    """Construct a ``SceneManager`` over *catalog*'s registries for a spy-based transition test.

    *effect_admin* records each transition's step; every other port is a spy.
    """
    return SceneManager(
        GameEngine(effect_controls=SpyEffectControls()),
        catalog.rule_registry,
        catalog.scene_registry,
        effect_admin,
        RecordingSceneReboot(),
    )


def make_scene_runtime(
    catalog: PackCatalog,
    outputs: list[EffectOutput] | None = None,
    *,
    capabilities: frozenset[str] = frozenset(),
    scene_reboot: SceneReboot | None = None,
    clock: Timer | None = None,
) -> SceneRuntime:
    """Construct a ``SceneRuntime`` over *catalog* drawing on *outputs*, with spies for its ports.

    No scene is active yet. Its network controls are a ``SpyNetworkControls``
    and, unless *scene_reboot* is given, its Reboots go to a
    ``RecordingSceneReboot``; omitting *clock* gives a wall clock.
    """
    return SceneRuntime(
        catalog,
        outputs if outputs is not None else [],
        SpyNetworkControls(),
        capabilities,
        scene_reboot if scene_reboot is not None else RecordingSceneReboot(),
        clock,
    )
