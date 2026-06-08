from __future__ import annotations

__all__ = ["Scene", "SceneManager"]

try:
    from collections.abc import Callable
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

try:
    from typing import Literal
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

from engine.engine import GameEngine, GameRule, Version
from engine.packs import PackRegistry
from engine.state import GameState, SceneControls, Scope


class Scene:
    """Declarative bundle describing a scene's rules, packs, and initial data.

    Carries no mutable runtime state.  Pass a zero-arg factory that returns a
    fresh ``Scene`` to ``SceneManager.register``; ``SceneManager`` calls the
    factory when the scene is first loaded so each load gets a clean instance.

    ``effect_packs`` and ``rule_packs`` are lists of ``(pack_name, "MAJOR.MINOR")``
    tuples referencing packs registered in the respective ``PackRegistry``.
    """

    __slots__ = (
        "__weakref__",
        "effect_packs",
        "initial_data",
        "rule_packs",
    )

    def __init__(
        self,
        effect_packs: list[tuple[str, str]],
        rule_packs: list[tuple[str, str]],
        initial_data: dict[str, object] | None = None,
    ) -> None:
        self.effect_packs = effect_packs
        self.rule_packs = rule_packs
        self.initial_data = initial_data


class SceneManager(SceneControls):
    """Manages a stack of active scenes, driving the game engine each tick.

    Construction::

        manager = SceneManager(engine, effect_registry, rule_registry)

    Registration::

        manager.register("main_menu", lambda: Scene(...))

    Driving the game loop::

        while running:
            manager.update()

    Scene transitions (``load``, ``overlay``, ``pop``) are deferred: they
    record a pending transition and the last call per tick wins.  The
    transition executes at the end of ``update()`` after ``engine.update``
    has processed all queued events.
    """

    __slots__ = (
        "_effect_registry",
        "_engine",
        "_pending",
        "_rule_registry",
        "_scenes",
        "_stack",
    )

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
        self._stack: list[tuple[Scene, GameState, list[GameRule]]] = []
        self._pending: (
            tuple[Literal["load"], Scene]
            | tuple[Literal["overlay"], Scene]
            | tuple[Literal["pop"]]
            | None
        ) = None

    def register(self, name: str, factory: Callable[[], Scene]) -> None:
        """Register *factory* — a zero-arg callable returning a ``Scene`` — for *name*."""
        self._scenes[name] = factory

    # ------------------------------------------------------------------
    # SceneControls interface — deferred transitions
    # ------------------------------------------------------------------

    def load(self, name: str) -> None:
        """Record a load transition for *name*; raises immediately if unknown or packs invalid."""
        if name not in self._scenes:
            raise ValueError("Unknown scene '" + name + "'")
        scene = self._scenes[name]()
        self._validate_packs(scene)
        self._pending = ("load", scene)

    def overlay(self, name: str) -> None:
        """Record an overlay transition for *name*; raises immediately if invalid."""
        if name not in self._scenes:
            raise ValueError("Unknown scene '" + name + "'")
        if not self._stack:
            raise ValueError("Cannot overlay: no active scene on stack")
        scene = self._scenes[name]()
        self._validate_packs(scene)
        self._pending = ("overlay", scene)

    @property
    def active_state(self) -> GameState | None:
        """The ``GameState`` for the top-most active scene, or ``None`` if the stack is empty."""
        if not self._stack:
            return None
        return self._stack[-1][1]

    def pop(self) -> None:
        """Record a pop transition; raises immediately if stack has ≤ 1 entry."""
        n = len(self._stack)
        if n <= 1:
            raise ValueError(
                "Cannot pop: stack has " + str(n) + " entr" + ("y" if n == 1 else "ies")
            )
        self._pending = ("pop",)

    # ------------------------------------------------------------------
    # Main loop driver
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Advance one tick: call ``engine.update`` then apply any pending transition.

        Skips ``engine.update`` when the stack is empty.  At most one pending
        transition executes per tick; the last ``load``/``overlay``/``pop``
        call within a tick wins.
        """
        if self._stack:
            self._engine.update(self._stack[-1][1])

        if self._pending is not None:
            pending = self._pending
            self._pending = None
            if pending[0] == "load":
                self._do_load(pending[1])
            elif pending[0] == "overlay":
                self._do_overlay(pending[1])
            else:
                self._do_pop()

    # ------------------------------------------------------------------
    # Internal transition helpers
    # ------------------------------------------------------------------

    def _validate_packs(self, scene: Scene) -> None:
        """Validate all pack versions; raises ``ValueError`` on mismatch."""
        for pack_name, min_version in scene.effect_packs:
            self._effect_registry.check_version(pack_name, Version.parse(min_version))
        for pack_name, min_version in scene.rule_packs:
            self._rule_registry.check_version(pack_name, Version.parse(min_version))

    def _resolve_rules(self, scene: Scene) -> list[GameRule]:
        """Return combined rules from all rule-pack items."""
        combined = []
        for pack_name, _ in scene.rule_packs:
            for item_name in self._rule_registry.items(pack_name):
                combined.append(self._rule_registry.get(pack_name, item_name, GameRule))
        return combined

    def _do_load(self, scene: Scene) -> None:
        """Execute a load transition: stop and unload all, create fresh state."""
        combined_rules = self._resolve_rules(scene)

        # Stop all effects on each outgoing scene top-down, then clear its queue
        for i in range(len(self._stack) - 1, -1, -1):
            _, st, _ = self._stack[i]
            st.effect_controls.stop_effect(Scope.ALL)
            st.clear_queue()

        self._stack = []
        state = self._engine.create_state(self, scene.initial_data)
        self._engine.set_rules(combined_rules)
        self._stack.append((scene, state, combined_rules))

    def _do_overlay(self, scene: Scene) -> None:
        """Execute an overlay transition: stop and suspend top, push new scene."""
        combined_rules = self._resolve_rules(scene)

        # Stop all effects on the suspended top, then clear its queue
        _, st, _ = self._stack[-1]
        st.effect_controls.stop_effect(Scope.ALL)
        st.clear_queue()

        # Push overlay without clearing the stack
        state = self._engine.create_state(self, scene.initial_data)
        self._engine.set_rules(combined_rules)
        self._stack.append((scene, state, combined_rules))

    def _do_pop(self) -> None:
        """Execute a pop transition: stop and unload top, restore scene below."""
        # Stop all effects on the top entry, then clear its queue and pop it
        _, st, _ = self._stack[-1]
        st.effect_controls.stop_effect(Scope.ALL)
        st.clear_queue()
        self._stack.pop()

        # Restore the now-active entry
        _, st, combined_rules = self._stack[-1]
        self._engine.set_rules(combined_rules)
        st.clear_queue()  # defensive clear on restored state
