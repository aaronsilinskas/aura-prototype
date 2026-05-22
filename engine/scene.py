from __future__ import annotations

from engine.packs import PackRegistry
from engine.version import Version

TYPE_CHECKING = False
try:
    from collections.abc import Callable
    from typing import TYPE_CHECKING
except ImportError:
    pass

if TYPE_CHECKING:
    from engine.engine import GameEngine

__all__ = ["Scene", "SceneControls", "SceneManager"]


class SceneControls:
    """Abstract interface for scene transitions called from within game rules.

    All methods raise ``NotImplementedError`` by default.  ``SceneManager``
    injects itself as the live implementation; standalone callers (e.g. rule
    unit tests) pass the base ``SceneControls()`` instance, which raises on
    any call.

    Transitions are deferred to end-of-tick — the transition is applied after
    ``engine.update(state)`` returns, not immediately inside the rule.
    """
    __slots__ = ()

    def load(self, name: str) -> None:
        """Replace the entire scene stack with the named scene."""
        raise NotImplementedError

    def overlay(self, name: str) -> None:
        """Push the named scene on top, suspending the current scene."""
        raise NotImplementedError

    def pop(self) -> None:
        """Unload the top scene and restore the scene below it."""
        raise NotImplementedError


class Scene:
    """Declarative scene bundle."""

    __slots__ = (
        "effect_packs",
        "initial_data",
        "on_load",
        "on_resume",
        "on_suspend",
        "on_unload",
        "rule_packs",
        "rules",
    )

    def __init__(
        self,
        rules: list[object],
        effect_packs: list[tuple[str, str]],
        rule_packs: list[tuple[str, str]],
        initial_data: dict[str, object] | None = None,
        on_load: Callable[[object], None] | None = None,
        on_unload: Callable[[object], None] | None = None,
        on_suspend: Callable[[object], None] | None = None,
        on_resume: Callable[[object], None] | None = None,
    ) -> None:
        self.rules = rules
        self.effect_packs = effect_packs
        self.rule_packs = rule_packs
        self.initial_data = initial_data
        self.on_load = on_load
        self.on_unload = on_unload
        self.on_suspend = on_suspend
        self.on_resume = on_resume


class SceneManager(SceneControls):
    """Applies deferred scene transitions around GameEngine updates."""

    __slots__ = ("_effect_registry", "_engine", "_pending", "_rule_registry", "_scenes", "_stack")

    def __init__(
        self,
        engine: GameEngine,
        effect_registry: PackRegistry,
        rule_registry: PackRegistry,
    ) -> None:
        self._engine = engine
        self._effect_registry = effect_registry
        self._rule_registry = rule_registry
        self._scenes: dict[str, Callable[[], Scene]] = {}
        self._stack: list[tuple[Scene, object, list[object]]] = []
        self._pending: tuple[str, Scene | None] | None = None

    def register(self, name: str, factory: Callable[[], Scene]) -> None:
        self._scenes[name] = factory

    def update(self) -> None:
        if self._stack:
            self._engine.update(self._stack[-1][1])
        pending = self._pending
        if pending is None:
            return
        self._pending = None
        operation, scene = pending
        if operation == "load":
            self._apply_load(scene)
            return
        if operation == "overlay":
            self._apply_overlay(scene)
            return
        self._apply_pop()

    def load(self, name: str) -> None:
        self._pending = ("load", self._resolve_scene(name))

    def overlay(self, name: str) -> None:
        if not self._stack:
            raise ValueError("Cannot overlay scene on empty stack")
        self._pending = ("overlay", self._resolve_scene(name))

    def pop(self) -> None:
        if len(self._stack) <= 1:
            raise ValueError("Cannot pop scene when stack has fewer than 2 entries")
        self._pending = ("pop", None)

    def _apply_load(self, scene: Scene | None) -> None:
        if scene is None:
            raise ValueError("Load requires a scene")
        state, combined_rules = self._build_entry(scene)
        if self._stack:
            _, active_state, _ = self._stack[-1]
            active_state.clear_queue()
            while self._stack:
                unload_scene, unload_state, _ = self._stack.pop()
                if unload_scene.on_unload is not None:
                    unload_scene.on_unload(unload_state.effect_controls)
        self._stack = [(scene, state, combined_rules)]
        self._engine.set_rules(combined_rules)
        if scene.on_load is not None:
            scene.on_load(state.effect_controls)

    def _apply_overlay(self, scene: Scene | None) -> None:
        if scene is None:
            raise ValueError("Overlay requires a scene")
        active_scene, active_state, _ = self._stack[-1]
        state, combined_rules = self._build_entry(scene)
        active_state.clear_queue()
        if active_scene.on_suspend is not None:
            active_scene.on_suspend(active_state.effect_controls)
        self._stack.append((scene, state, combined_rules))
        self._engine.set_rules(combined_rules)
        if scene.on_load is not None:
            scene.on_load(state.effect_controls)

    def _apply_pop(self) -> None:
        unload_scene, unload_state, _ = self._stack[-1]
        unload_state.clear_queue()
        if unload_scene.on_unload is not None:
            unload_scene.on_unload(unload_state.effect_controls)
        self._stack.pop()
        restored_scene, restored_state, restored_rules = self._stack[-1]
        self._engine.set_rules(restored_rules)
        restored_state.clear_queue()
        if restored_scene.on_resume is not None:
            restored_scene.on_resume(restored_state.effect_controls)

    def _resolve_scene(self, name: str) -> Scene:
        factory = self._scenes.get(name)
        if factory is None:
            raise ValueError("Unknown scene '" + name + "'")
        scene = factory()
        self._validate_scene_packs(scene)
        return scene

    def _build_entry(self, scene: Scene) -> tuple[object, list[object]]:
        combined_rules = self._combined_rules(scene)
        state = self._engine.create_state(self, scene.initial_data)
        return state, combined_rules

    def _validate_scene_packs(self, scene: Scene) -> None:
        for pack_name, min_version in scene.effect_packs:
            self._effect_registry.check_version(pack_name, Version.parse(min_version))
        for pack_name, min_version in scene.rule_packs:
            self._rule_registry.check_version(pack_name, Version.parse(min_version))

    def _combined_rules(self, scene: Scene) -> list[object]:
        rules = list(scene.rules)
        for pack_name, _ in scene.rule_packs:
            for item_name in self._rule_registry.items(pack_name):
                module = self._rule_registry.get(pack_name, item_name)
                rule = getattr(module, "RULE", None)
                if rule is None:
                    raise ValueError(
                        "Rule module '"
                        + pack_name
                        + "."
                        + item_name
                        + "' must export RULE"
                    )
                rules.append(rule)
        return rules
