from __future__ import annotations

__all__ = ["PackReference", "Scene", "SceneLocalRegistry", "SceneManager", "SceneRegistry"]


try:
    from collections.abc import Mapping, Sequence
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

try:
    from typing import Literal, TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

from engine.capabilities import MissingCapabilityError
from engine.effects.admin import EffectAdmin, HeldEffects, SceneView
from engine.engine import GameRule, Version
from engine.packs import PackRegistry, UnknownItemError, load_item
from engine.settings import Settings
from engine.state import (
    EffectControls,
    GameState,
    NetworkControls,
    SceneControls,
    SceneReboot,
    SceneRun,
)


class SceneLocalRegistry:
    """Single-namespace registry for one scene's local items (rules or effects).

    Maps item name → loaded item, sharing item-loading internals (import,
    attribute extraction, isinstance check, cache) with ``PackRegistry`` via
    ``load_item``.  No version concept.

    Built only by ``engine.pack_catalog.scan_pack_roots``, which discovers the
    items and sets the attribute they export (``BUILD`` or ``RULE``).
    ``SceneLocalRegistry()`` is a valid empty registry.

    Example::

        rule = scene.local_rule_registry.get("my_rule", GameRule)
    """

    __slots__ = ("_cache", "_item_attr", "_item_names", "_module_prefix")

    def __init__(self) -> None:
        # Empty until ``_from_items`` fills it and sets the export attribute;
        # until then every get() misses before reading it.
        self._item_attr: str = ""
        self._item_names: set[str] = set()
        self._module_prefix: str = ""
        self._cache: dict[str, object] = {}

    @staticmethod
    def _from_items(item_attr: str, item_names: set[str], module_prefix: str) -> SceneLocalRegistry:
        """Return a registry of *item_names* under *module_prefix* exporting *item_attr*.

        The ``PackCatalog`` construction path.
        """
        registry = SceneLocalRegistry()
        registry._item_attr = item_attr
        registry._item_names = item_names
        registry._module_prefix = module_prefix
        return registry

    def get(self, item_name: str, expected_class: type[T]) -> T:
        """Return the export (``BUILD`` or ``RULE``) of *item_name*.

        The item is imported on first access and the result is cached.

        Raises:
            UnknownItemError: if *item_name* is not in the recorded set.
            MissingItemAttributeError: if the module lacks the export.
            ItemTypeError: if the export is not an instance of *expected_class*.
        """
        if item_name not in self._item_names:
            raise UnknownItemError(item_name, sorted(self._item_names))

        if item_name in self._cache:
            return self._cache[item_name]  # type: ignore[return-value]  # checked when loaded

        full_module = self._module_prefix + "." + item_name
        context = f"Local item '{item_name}'"
        value = load_item(full_module, self._item_attr, context, expected_class)
        self._cache[item_name] = value
        return value

    def items(self) -> list[str]:
        """Return all registered item names in alphabetical order."""
        return sorted(self._item_names)


class PackReference:
    """One entry of a scene's ``effect_packs`` or ``rule_packs``.

    *version* is the minimum compatible version: the installed pack must have
    the same major and at least this minor. *settings* holds the scene's
    Setting overrides for a Rule pack, exactly as written in ``scene.json``;
    the scan checks them when it resolves the scene's Settings. An effect
    pack's reference takes no overrides, so its *settings* is always empty.
    """

    __slots__ = ("name", "settings", "version")

    def __init__(
        self, name: str, version: Version, settings: dict[str, object] | None = None
    ) -> None:
        self.name = name
        self.version = version
        self.settings = settings if settings is not None else {}


class Scene:
    """One scene's complete, read-only record: its packs, Settings and local items.

    Built once, complete, by the ``PackCatalog`` scan (or in memory by tests)
    and shared by every holder afterwards: ``SceneRegistry.get`` returns the
    stored record itself. Nothing mutates a ``Scene`` or its fields after it
    is built; callers must treat the sound map, Settings and pack references
    as read-only.

    ``effect_packs`` and ``rule_packs`` are ordered ``PackReference`` sequences
    naming packs in the respective ``PackRegistry``.  ``rule_packs`` order sets
    the order of rules across packs.

    ``version`` is the scene's own declared version from ``scene.json``,
    format-checked by the scan; nothing reads it yet.

    ``ir_codec`` names the scene's declared IR wire-frame codec, defaulting to
    ``"aura"``, which ``SceneRegistry.ir_codec_for`` reads.  A plain string
    only — the engine never imports the codec classes themselves, preserving
    the one-way ``engine`` → ``hardware`` layering.  Resolving the name to a
    codec is a ``hardware``-layer concern.

    ``settings`` is the scene's resolved ``Settings``, which ``SceneManager``
    hands to each ``GameState`` it creates for the scene.

    ``required_capabilities`` is what the scene's ``requires`` lists plus what
    each of its Rule packs lists; ``SceneRegistry`` answers from it.

    ``local_rule_registry`` and ``local_effect_registry`` are the
    ``SceneLocalRegistry`` instances for the scene's scene-local rules and
    effects (items export ``RULE`` and ``BUILD``).  ``local_sound_map`` is the
    bare-keyed ``{stem: path}`` map of its scene-local sounds (its ``sounds/``
    subdirectory).  ``SceneManager`` resolves the local rules into the scene's
    ``SceneRun``; the local effects and sounds go into its Scene view, which the
    effect system installs on every transition into the scene (ADR-0008).
    """

    __slots__ = (
        "__weakref__",
        "effect_packs",
        "ir_codec",
        "local_effect_registry",
        "local_rule_registry",
        "local_sound_map",
        "required_capabilities",
        "rule_packs",
        "settings",
        "version",
    )

    def __init__(
        self,
        effect_packs: Sequence[PackReference],
        rule_packs: Sequence[PackReference],
        version: Version | None = None,
        ir_codec: str = "aura",
        local_rule_registry: SceneLocalRegistry | None = None,
        local_effect_registry: SceneLocalRegistry | None = None,
        local_sound_map: dict[str, str] | None = None,
        settings: Settings | None = None,
        required_capabilities: frozenset[str] = frozenset(),
    ) -> None:
        self.settings = settings if settings is not None else Settings()
        self.effect_packs = effect_packs
        self.rule_packs = rule_packs
        self.version = version
        self.ir_codec = ir_codec
        self.local_rule_registry = (
            local_rule_registry if local_rule_registry is not None else SceneLocalRegistry()
        )
        self.local_effect_registry = (
            local_effect_registry if local_effect_registry is not None else SceneLocalRegistry()
        )
        self.local_sound_map = local_sound_map if local_sound_map is not None else {}
        self.required_capabilities = required_capabilities


class SceneRegistry:
    """The installed scenes, each a ``Scene`` record keyed by name.

    Built by ``scan_pack_roots`` from the scanned records, or by tests from
    in-memory ones::

        registry = SceneRegistry({"forest": forest})
        scene = registry.get("forest")  # the stored record itself

    The registry holds *scenes* as given, without copying it, so callers
    must not mutate the mapping afterwards.
    """

    __slots__ = ("_scenes",)

    def __init__(self, scenes: Mapping[str, Scene]) -> None:
        self._scenes = scenes

    def get(self, name: str) -> Scene:
        """Return the stored ``Scene`` for *name*, the same record on every call.

        Raises:
            ValueError: if *name* is not in the registry.
        """
        scene = self._scenes.get(name)
        if scene is None:
            raise ValueError(f"Unknown scene '{name}'")
        return scene

    def ir_codec_for(self, name: str) -> str:
        """Return *name*'s declared ``ir_codec`` string (default ``"aura"``).

        Raises:
            ValueError: if *name* is not in the registry.
        """
        return self.get(name).ir_codec

    def required_capabilities(self, name: str) -> frozenset[str]:
        """Return *name*'s Required capabilities.

        Raises:
            ValueError: if *name* is not in the registry.
        """
        return self.get(name).required_capabilities

    def missing_capabilities(self, name: str, capabilities: frozenset[str]) -> frozenset[str]:
        """Return the Required capabilities of *name* that are not in *capabilities*.

        Raises:
            ValueError: if *name* is not in the registry.
        """
        return self.required_capabilities(name) - capabilities

    def names(self) -> list[str]:
        """Return the names of all scenes in the registry, sorted alphabetically."""
        return sorted(self._scenes)

    def resolve_known(self, name: str) -> str:
        """Return *name* if it is in the registry, else raise naming the known scenes.

        The single known-scene check, shared by the Scene boot
        (``app.scene_composition.build_scene_boot``, the boot-time guard) and
        ``SceneManager.reboot_into`` (the Button-B fail-fast guard) so the
        check and its message have exactly one implementation.
        """
        if name in self._scenes:
            return name
        raise ValueError(f"unknown scene {name!r}; known scenes: {', '.join(self.names())}")


def _scene_view(scene: Scene) -> SceneView:
    """Return *scene*'s Scene view: its local effects and sounds, and its declared packs."""
    return SceneView(
        scene.local_effect_registry,
        scene.local_sound_map,
        frozenset(pack.name for pack in scene.effect_packs),
    )


class _SceneStackEntry:
    """One entry in ``SceneManager``'s scene stack.  Internal use only.

    ``run`` is the scene's SceneRun: its state and its rules.  ``view`` is
    the scene's Scene view, built once and handed to every ``EffectAdmin``
    step that brings this entry to the top.  ``held`` is the
    covered scene's effects and merge strategies, returned by
    ``EffectAdmin.cover`` when ``overlay`` pushed this entry and given to
    ``EffectAdmin.uncover`` when it is popped — ``None`` for the boot
    scene's base entry, which covers nothing.  Folding the bundle into the
    same entry as the scene stack means the two stacks can never desync.
    """

    __slots__ = ("held", "run", "scene", "view")

    def __init__(
        self,
        scene: Scene,
        run: SceneRun,
        view: SceneView,
        held: HeldEffects | None,
    ) -> None:
        self.scene = scene
        self.run = run
        self.view = view
        self.held = held


class SceneManager(SceneControls):
    """Manages a stack of active scenes, each a ``SceneRun``, ticking the top one.

    Construction::

        manager = SceneManager(
            effect_controls,
            network_controls,
            capabilities,
            rule_registry,
            scene_registry,
            effect_admin,
            scene_reboot,
        )

    Driving the game loop, with the tick's elapsed time from the clock its
    caller (``SceneRuntime``) holds::

        while running:
            manager.update(elapsed)

    The boot composition makes the first scene active with
    ``activate_boot_scene``, which applies at once and is not on
    ``SceneControls``: rules change scene by Reboot (ADR-0005).

    Scene transitions (``overlay``, ``pop``) are deferred: they
    record a pending transition and the last call per tick wins.  The
    transition executes at the end of ``update()`` after the top
    ``SceneRun`` has dispatched all queued events.

    Scene lookup delegates entirely to *scene_registry*:
    ``activate_boot_scene`` and ``overlay`` call ``scene_registry.get(name)``,
    which raises ``ValueError`` for unknown names.

    Each scene's ``GameState`` carries *effect_controls*, *network_controls*,
    *capabilities*, this manager as its ``SceneControls`` and the scene's
    Settings.

    *capabilities* are the device's Capabilities. Every transition
    into a scene (``activate_boot_scene``, ``overlay``, ``reboot_into``,
    ``reboot_to_previous``) checks the target's Required capabilities against
    them and raises ``MissingCapabilityError`` before recording, persisting
    or resetting anything; ``pop`` returns to a scene that already ran and
    does not check. ``can_run`` asks the same question without raising.

    *effect_admin* is the scene-transition face of the same effect system as
    *effect_controls* (two faces of one ``EffectManager`` instance). Every
    transition makes exactly one call to it, carrying the Scene view of the
    scene it brings to the top: ``activate_boot_scene`` enters, ``overlay``
    covers and ``pop`` uncovers. No transition reaches the effect system
    through a stack entry's ``state.effect_controls``. The IR codec is not
    touched by ``overlay`` or ``pop``: an overlay runs on the covered scene's
    codec (ADR-0005).

    *scene_reboot* is the injected ``SceneReboot`` port ``reboot_into``/
    ``reboot_to_previous`` delegate to (its ``previous_scene`` names the
    target ``reboot_to_previous`` checks). Unlike *effect_admin* it plays no
    role in activation, ``overlay`` or ``pop`` — it exists solely for the
    two reboot methods, which apply immediately and synchronously rather
    than joining the deferred-transition queue.
    """

    __slots__ = (
        "_capabilities",
        "_effect_admin",
        "_effect_controls",
        "_network_controls",
        "_pending",
        "_rule_registry",
        "_scene_reboot",
        "_scene_registry",
        "_stack",
    )

    def __init__(
        self,
        effect_controls: EffectControls,
        network_controls: NetworkControls,
        capabilities: frozenset[str],
        rule_registry: PackRegistry,
        scene_registry: SceneRegistry,
        effect_admin: EffectAdmin,
        scene_reboot: SceneReboot,
    ) -> None:
        self._effect_controls = effect_controls
        self._network_controls = network_controls
        self._capabilities = capabilities
        self._rule_registry = rule_registry
        self._scene_registry = scene_registry
        self._effect_admin = effect_admin
        self._scene_reboot = scene_reboot
        self._stack: list[_SceneStackEntry] = []
        self._pending: tuple[Literal["overlay"], Scene] | tuple[Literal["pop"]] | None = None

    # ------------------------------------------------------------------
    # Boot — not on SceneControls, so rules can't reach it
    # ------------------------------------------------------------------

    def activate_boot_scene(self, name: str) -> None:
        """Make *name* the active scene, at once, on Split for every scope.

        Called once by the boot composition; a rule changes scene by
        Reboot instead.

        Raises:
            ValueError: *name* is not in the scene registry, or a scene is
                already active.
            MissingCapabilityError: the device can't run *name*; nothing is
                activated.
        """
        if self._stack:
            raise ValueError("Cannot activate boot scene: a scene is already active")
        scene = self._scene_registry.get(name)
        self._require_runnable(name)
        entry = _SceneStackEntry(scene, self._new_run(scene), _scene_view(scene), held=None)
        self._stack.append(entry)
        self._effect_admin.enter_boot_scene(entry.view)

    # ------------------------------------------------------------------
    # SceneControls interface — deferred transitions
    # ------------------------------------------------------------------

    def overlay(self, name: str) -> None:
        """Record an overlay transition for *name*; raises immediately if invalid.

        Raises:
            MissingCapabilityError: the device can't run *name*; nothing is
                recorded.
        """
        if not self._stack:
            raise ValueError("Cannot overlay: no active scene on stack")
        scene = self._scene_registry.get(name)
        self._require_runnable(name)
        self._pending = ("overlay", scene)

    def can_run(self, name: str) -> bool:
        """Whether the device has every Required capability of *name*.

        Raises:
            ValueError: if *name* is not in the scene registry.
        """
        return not self._scene_registry.missing_capabilities(name, self._capabilities)

    def _require_runnable(self, name: str) -> None:
        missing = self._scene_registry.missing_capabilities(name, self._capabilities)
        if missing:
            raise MissingCapabilityError(missing, name)

    @property
    def active_state(self) -> GameState | None:
        """The ``GameState`` for the top-most active scene, or ``None`` if the stack is empty."""
        if not self._stack:
            return None
        return self._stack[-1].run.state

    def pop(self) -> None:
        """Record a pop transition; raises immediately if stack has ≤ 1 entry."""
        n = len(self._stack)
        if n <= 1:
            raise ValueError(f"Cannot pop: stack has {n} entr{'y' if n == 1 else 'ies'}")
        self._pending = ("pop",)

    # ------------------------------------------------------------------
    # SceneControls interface — immediate reboot (not deferred)
    # ------------------------------------------------------------------

    def reboot_into(self, target: str) -> None:
        """Validate *target*, then delegate to the injected ``SceneReboot`` port.

        Raises ``ValueError`` naming the known scenes, and persists nothing,
        when *target* is not in the scene registry — a typo caught here
        (e.g. at the Button-B press) never reaches the port, so it never
        persists a name that would brick the next boot. A known *target*
        the device can run delegates straight through;
        ``SceneReboot.reboot_into`` reboots and never returns.

        Raises:
            MissingCapabilityError: the device can't run *target*; nothing
                is persisted and the device doesn't reset.
        """
        self._scene_registry.resolve_known(target)
        self._require_runnable(target)
        self._scene_reboot.reboot_into(target)

    def reboot_to_previous(self) -> None:
        """Check the port's ``previous_scene``, then delegate to the port.

        With nothing recorded the port's own no-op handles it. A recorded
        scene is not checked against the registry here: an unknown one is
        caught at boot by ``SceneRegistry.resolve_known``, exactly like the
        Persisted scene.

        Raises:
            MissingCapabilityError: the device can't run the recorded scene;
                nothing is persisted and the device doesn't reset.
        """
        previous = self._scene_reboot.previous_scene()
        if previous is not None and previous in self._scene_registry.names():
            self._require_runnable(previous)
        self._scene_reboot.reboot_to_previous()

    # ------------------------------------------------------------------
    # Main loop driver
    # ------------------------------------------------------------------

    def update(self, elapsed: float) -> None:
        """Tick the top ``SceneRun`` by *elapsed* seconds, then apply any pending transition.

        Ticks nothing when the stack is empty; a covered scene is never
        ticked, so its game time stops.  At most one pending transition
        executes per tick; the last ``overlay``/``pop`` call within a tick
        wins.
        """
        if self._stack:
            self._stack[-1].run.tick(elapsed)

        if self._pending is not None:
            pending = self._pending
            self._pending = None
            if pending[0] == "overlay":
                self._do_overlay(pending[1])
            else:
                self._do_pop()

    # ------------------------------------------------------------------
    # Internal transition helpers
    # ------------------------------------------------------------------

    def _resolve_rules(self, scene: Scene) -> list[GameRule]:
        """Return combined rules: shared-pack items first, scene-local items after."""
        combined = []
        for pack in scene.rule_packs:
            for item_name in self._rule_registry.items(pack.name):
                combined.append(self._rule_registry.get(pack.name, item_name, GameRule))
        for item_name in scene.local_rule_registry.items():
            combined.append(scene.local_rule_registry.get(item_name, GameRule))
        return combined

    def _new_run(self, scene: Scene) -> SceneRun:
        state = GameState(
            self._effect_controls,
            self,
            self._network_controls,
            settings=scene.settings,
            capabilities=self._capabilities,
        )
        return SceneRun(state, self._resolve_rules(scene))

    def _do_overlay(self, scene: Scene) -> None:
        """Suspend the current top, covering its effects, and push *scene* above it."""
        run = self._new_run(scene)
        view = _scene_view(scene)
        held = self._effect_admin.cover(view)
        self._stack.append(_SceneStackEntry(scene, run, view, held))

    def _do_pop(self) -> None:
        """Remove the top entry and uncover the scene below it."""
        popped = self._stack.pop()
        # pop() rejects a stack of size <= 1, so the popped entry is always one
        # overlay() pushed — never the boot scene's base entry, whose held is
        # None. Narrows the type for uncover.
        assert popped.held is not None
        revealed = self._stack[-1]
        self._effect_admin.uncover(popped.held, revealed.view)
