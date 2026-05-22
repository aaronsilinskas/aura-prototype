__all__ = ["Scene", "SceneControls", "SceneManager"]

try:
    from collections.abc import Callable
except ImportError:
    Callable = object  # type: ignore[assignment,misc]  # CircuitPython/MicroPython fallback

from engine.version import Version


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
    """Declarative bundle describing a scene's rules, packs, and lifecycle hooks.

    Carries no mutable runtime state.  Pass a zero-arg factory that returns a
    fresh ``Scene`` to ``SceneManager.register``; ``SceneManager`` calls the
    factory when the scene is first loaded so each load gets a clean instance.

    ``effect_packs`` and ``rule_packs`` are lists of ``(pack_name, "MAJOR.MINOR")``
    tuples referencing packs registered in the respective ``PackRegistry``.

    Lifecycle callbacks receive only ``effect_controls``::

        def on_load(effect_controls: EffectControls) -> None: ...
    """

    __slots__ = (
        "__weakref__",
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
        rules: list,
        effect_packs: list,
        rule_packs: list,
        initial_data: dict | None = None,
        on_load: Callable | None = None,
        on_unload: Callable | None = None,
        on_suspend: Callable | None = None,
        on_resume: Callable | None = None,
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
        engine: object,
        effect_registry: object,
        rule_registry: object,
    ) -> None:
        self._engine = engine
        self._effect_registry = effect_registry
        self._rule_registry = rule_registry
        self._scenes: dict = {}
        self._stack: list = []
        self._pending = None  # tuple (kind, name) or None

    def register(self, name: str, factory: Callable) -> None:
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

    def pop(self) -> None:
        """Record a pop transition; raises immediately if stack has ≤ 1 entry."""
        n = len(self._stack)
        if n <= 1:
            raise ValueError(
                "Cannot pop: stack has " + str(n) + " entr" + ("y" if n == 1 else "ies")
            )
        self._pending = ("pop", None)

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
            kind, arg = self._pending
            self._pending = None
            if kind == "load":
                self._do_load(arg)
            elif kind == "overlay":
                self._do_overlay(arg)
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

    def _resolve_rules(self, scene: Scene) -> list:
        """Return combined rules: *scene.rules* followed by all rule-pack items."""
        combined = list(scene.rules)
        for pack_name, _ in scene.rule_packs:
            for item_name in self._rule_registry.items(pack_name):
                combined.append(self._rule_registry.get(pack_name, item_name))
        return combined

    def _do_load(self, scene: Scene) -> None:
        """Execute a load transition: unload all, create fresh state, fire on_load."""
        combined_rules = self._resolve_rules(scene)

        # Fire on_unload top-down and clear each state's queue
        for i in range(len(self._stack) - 1, -1, -1):
            s, st, _ = self._stack[i]
            if s.on_unload is not None:
                s.on_unload(st.effect_controls)
            st.clear_queue()

        self._stack = []
        state = self._engine.create_state(self, scene.initial_data)
        self._engine.set_rules(combined_rules)
        self._stack.append((scene, state, combined_rules))

        if scene.on_load is not None:
            scene.on_load(state.effect_controls)

    def _do_overlay(self, scene: Scene) -> None:
        """Execute an overlay transition: suspend top, push new scene."""
        combined_rules = self._resolve_rules(scene)

        # Suspend current top
        s, st, _ = self._stack[-1]
        if s.on_suspend is not None:
            s.on_suspend(st.effect_controls)
        st.clear_queue()

        # Push overlay without clearing the stack
        state = self._engine.create_state(self, scene.initial_data)
        self._engine.set_rules(combined_rules)
        self._stack.append((scene, state, combined_rules))

    def _do_pop(self) -> None:
        """Execute a pop transition: unload top, restore and resume scene below."""
        # Unload the top entry
        s, st, _ = self._stack[-1]
        if s.on_unload is not None:
            s.on_unload(st.effect_controls)
        st.clear_queue()
        self._stack.pop()

        # Restore the now-active entry
        s, st, combined_rules = self._stack[-1]
        self._engine.set_rules(combined_rules)
        st.clear_queue()  # defensive clear on restored state
        if s.on_resume is not None:
            s.on_resume(st.effect_controls)
