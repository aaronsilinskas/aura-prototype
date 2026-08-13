from __future__ import annotations

__all__ = ["Scene", "SceneLocalRegistry", "SceneManager", "SceneRegistry"]

import json
import os

try:
    from collections.abc import Callable, Sequence
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

try:
    from typing import Literal, TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython/MicroPython

import engine._path as _path
from engine.audio import scan_sound_dir
from engine.engine import GameEngine, GameRule, Version
from engine.packs import PackRegistry, UnknownItemError, load_item, scan_item_names
from engine.state import EffectAdmin, GameState, MergeStrategy, SceneControls, Scope

_REQUIRED_KEYS = frozenset(("version", "effect_packs", "rule_packs"))


class SceneLocalRegistry:
    """Single-namespace registry for one scene's local items (rules or effects).

    Maps item name → loaded item, sharing item-loading internals (import,
    attribute extraction, isinstance check, cache) with ``PackRegistry`` via
    ``load_item``.  No version concept.

    Populated at scene discovery time via ``scan_dir``; accessed via
    ``get`` and ``items``.

    Example::

        registry = SceneLocalRegistry(item_attr="RULE")
        registry.scan_dir("/path/to/scene/rules", "packs.scenes.forest.rules")
        rule = registry.get("my_rule", GameRule)
    """

    __slots__ = ("_cache", "_item_attr", "_item_names", "_module_prefix")

    def __init__(self, item_attr: str) -> None:
        self._item_attr = item_attr
        self._item_names: set[str] = set()
        self._module_prefix: str = ""
        self._cache: dict[str, object] = {}

    def scan_dir(self, item_dir: str, module_prefix: str) -> None:
        """Populate from item_dir using scan_item_names. Single-shot; missing/non-dir is a no-op."""
        if not _path.isdir(item_dir):
            return
        self._item_names = scan_item_names(item_dir)
        self._module_prefix = module_prefix

    def get(self, item_name: str, expected_class: type[T]) -> T:
        """Return the *item_attr* attribute of *item_name*.

        The item is imported on first access and the result is cached.

        Raises:
            UnknownItemError: if *item_name* is not in the recorded set.
            MissingItemAttributeError: if the module has no attribute named
                *item_attr*.
            ItemTypeError: if the attribute value is not an instance of
                *expected_class*.
        """
        if item_name not in self._item_names:
            raise UnknownItemError(item_name, sorted(self._item_names))

        if item_name in self._cache:
            return self._cache[item_name]  # type: ignore[return-value]

        full_module = self._module_prefix + "." + item_name
        context = f"Local item '{item_name}'"
        value = load_item(full_module, self._item_attr, context, expected_class)
        self._cache[item_name] = value
        return value  # type: ignore[return-value]

    def items(self) -> list[str]:
        """Return all registered item names in alphabetical order."""
        return sorted(self._item_names)


class Scene:
    """Declarative bundle describing a scene's rules, packs, and initial data.

    Carries no mutable runtime state.  Pass a zero-arg factory that returns a
    fresh ``Scene`` to ``SceneManager.register``; ``SceneManager`` calls the
    factory when the scene is first loaded so each load gets a clean instance.

    ``effect_packs`` and ``rule_packs`` are sequences of ``(pack_name, "MAJOR.MINOR")``
    pairs referencing packs registered in the respective ``PackRegistry``.  JSON
    discovery yields lists-of-lists; factory-built scenes may pass tuples — hence
    the ``Sequence[Sequence[str]]`` typing.

    ``version`` is the scene's own declared version, parsed from ``scene.json`` at
    discovery time.  It is informational for now — format-validated and stored, but
    not checked against any requirement.

    ``local_rule_registry`` is the ``SceneLocalRegistry`` for this scene's
    scene-local rules.  It is built once at discovery and shared across fresh
    ``Scene`` instances; mutable import-cache state lives on the registry, not
    on the ``Scene`` itself.

    ``local_effect_registry`` is the ``SceneLocalRegistry`` for this scene's
    scene-local effects (items expose a ``BUILD`` ``EffectBuilder``).  Built
    once at discovery and shared across fresh ``Scene`` instances.

    ``local_sound_map`` is a bare-keyed ``{stem: path}`` map of this scene's
    scene-local sounds (its ``sounds/`` subdirectory).  Built once at discovery
    via ``scan_sound_dir``; unlike ``local_rule_registry``/``local_effect_registry``
    it is a plain mutable dict rather than an encapsulated registry, so — like
    ``initial_data`` — each fresh ``Scene`` from ``SceneRegistry.get`` receives its
    own copy, keeping mutation from poisoning future loads.  Purely additive for
    now — no consumer resolves it yet.
    """

    __slots__ = (
        "__weakref__",
        "effect_packs",
        "initial_data",
        "local_effect_registry",
        "local_rule_registry",
        "local_sound_map",
        "rule_packs",
        "version",
    )

    def __init__(
        self,
        effect_packs: Sequence[Sequence[str]],
        rule_packs: Sequence[Sequence[str]],
        initial_data: dict[str, object] | None = None,
        version: Version | None = None,
        local_rule_registry: SceneLocalRegistry | None = None,
        local_effect_registry: SceneLocalRegistry | None = None,
        local_sound_map: dict[str, str] | None = None,
    ) -> None:
        self.effect_packs = effect_packs
        self.rule_packs = rule_packs
        self.initial_data = initial_data
        self.version = version
        self.local_rule_registry = (
            local_rule_registry
            if local_rule_registry is not None
            else SceneLocalRegistry(item_attr="RULE")
        )
        self.local_effect_registry = (
            local_effect_registry
            if local_effect_registry is not None
            else SceneLocalRegistry(item_attr="BUILD")
        )
        self.local_sound_map = local_sound_map if local_sound_map is not None else {}


class _SceneEntry:
    """Stored metadata for a single discovered scene.  Internal use only."""

    __slots__ = (
        "effect_packs",
        "initial_data",
        "local_effect_registry",
        "local_rule_registry",
        "local_sound_map",
        "rule_packs",
        "source_path",
        "version",
    )

    def __init__(
        self,
        version: Version,
        effect_packs: Sequence[Sequence[str]],
        rule_packs: Sequence[Sequence[str]],
        initial_data: dict[str, object] | None,
        source_path: str,
        local_rule_registry: SceneLocalRegistry,
        local_effect_registry: SceneLocalRegistry,
        local_sound_map: dict[str, str],
    ) -> None:
        self.version = version
        self.effect_packs = effect_packs
        self.rule_packs = rule_packs
        self.initial_data = initial_data
        self.source_path = source_path
        self.local_rule_registry = local_rule_registry
        self.local_effect_registry = local_effect_registry
        self.local_sound_map = local_sound_map


class SceneRegistry:
    """Auto-discovers JSON-described scenes from a directory.

    Construction::

        registry = SceneRegistry()

    Scanning::

        registry.scan_dir("/path/to/scenes", "packs.scenes")

    Scene access::

        scene = registry.get("forest")  # fresh Scene each call

    In-memory registration (test escape hatch)::

        registry.register("test_scene", lambda: Scene(...))
    """

    __slots__ = ("_factories", "_scanned_dirs", "_scenes")

    def __init__(self) -> None:
        self._scenes: dict[str, _SceneEntry] = {}
        self._factories: dict[str, Callable[[], Scene]] = {}
        self._scanned_dirs: set[str] = set()

    def scan_dir(self, path: str, module_prefix: str) -> None:
        """Scan *path* for subdirectories that contain a ``scene.json``.

        Each such subdirectory is registered as a scene with the directory name
        as its scene name.  If a scene folder contains a ``rules/`` subdirectory,
        every ``.py`` file in it (except ``__init__.py`` and any ``tests/`` subdir)
        is recorded as a scene-local rule item in that scene's
        ``SceneLocalRegistry``.  The local module prefix for each item is derived
        as ``module_prefix + "." + scene_name + ".rules"``.  If a scene folder
        contains a ``sounds/`` subdirectory, every ``*.wav`` file in it is recorded
        in that scene's bare-keyed ``local_sound_map`` (``stem`` → path).

        *module_prefix* is the dotted import root for scene directories (e.g.
        ``"packs.scenes"``).  It is required; path-relative derivation is
        rejected as fragile.

        All validation (required fields, version format) happens here so that
        misconfigured scenes fail at startup.

        This method is idempotent: calling it a second time with the same *path*
        is a no-op.  Discovering a scene name that was already registered from a
        **different** source path raises ``ValueError``.

        Raises:
            ValueError: if a required field (``version``, ``effect_packs``,
                ``rule_packs``) is missing from ``scene.json``.
            ValueError: if ``version`` cannot be parsed by ``Version.parse``.
            ValueError: if the same scene name is found in two different paths.
        """
        norm_path = _path.normpath(path)
        if norm_path in self._scanned_dirs:
            return
        self._scanned_dirs.add(norm_path)

        for entry in os.listdir(norm_path):
            scene_dir = _path.join(norm_path, entry)
            scene_json_path = _path.join(scene_dir, "scene.json")
            if not _path.isdir(scene_dir) or not _path.isfile(scene_json_path):
                continue

            scene_name = entry

            if scene_name in self._scenes:
                existing = self._scenes[scene_name]
                if existing.source_path != norm_path:
                    raise ValueError(
                        f"Scene '{scene_name}' already registered from "
                        + f"'{existing.source_path}'; cannot register the same scene name "
                        + f"from '{norm_path}'"
                    )
                continue

            with open(scene_json_path) as fh:
                data = json.load(fh)

            for key in _REQUIRED_KEYS:
                if key not in data:
                    raise ValueError(
                        f"Scene '{scene_name}' in '{norm_path}' is missing required key "
                        + f"'{key}' in scene.json"
                    )

            try:
                version = Version.parse(data["version"])
            except (ValueError, IndexError, TypeError) as exc:
                raise ValueError(
                    f"Scene '{scene_name}' in '{norm_path}' has malformed version "
                    + f"'{data['version']}': {exc}"
                ) from exc

            initial_data = data.get("initial_data")

            local_rule_registry = SceneLocalRegistry(item_attr="RULE")
            local_rule_registry.scan_dir(
                _path.join(scene_dir, "rules"),
                module_prefix + "." + scene_name + ".rules",
            )
            local_effect_registry = SceneLocalRegistry(item_attr="BUILD")
            local_effect_registry.scan_dir(
                _path.join(scene_dir, "effects"),
                module_prefix + "." + scene_name + ".effects",
            )
            local_sound_map = scan_sound_dir(_path.join(scene_dir, "sounds"))

            self._scenes[scene_name] = _SceneEntry(
                version=version,
                effect_packs=data["effect_packs"],
                rule_packs=data["rule_packs"],
                initial_data=initial_data,
                source_path=norm_path,
                local_rule_registry=local_rule_registry,
                local_effect_registry=local_effect_registry,
                local_sound_map=local_sound_map,
            )

    def get(self, name: str) -> Scene:
        """Return a fresh ``Scene`` for *name*.

        JSON-discovered scenes share the parsed ``Version`` across calls but
        receive their own copy of ``initial_data`` and ``local_sound_map`` so
        that mutations cannot poison future loads.  Factory-registered scenes
        return whatever the factory produces.

        Raises:
            ValueError: if *name* is not registered.
        """
        factory = self._factories.get(name)
        if factory is not None:
            return factory()

        entry = self._scenes.get(name)
        if entry is None:
            raise ValueError(f"Unknown scene '{name}'")

        initial_data = dict(entry.initial_data) if entry.initial_data is not None else None
        return Scene(
            effect_packs=entry.effect_packs,
            rule_packs=entry.rule_packs,
            initial_data=initial_data,
            version=entry.version,
            local_rule_registry=entry.local_rule_registry,
            local_effect_registry=entry.local_effect_registry,
            local_sound_map=dict(entry.local_sound_map),
        )

    def names(self) -> list[str]:
        """Return all registered scene names sorted alphabetically."""
        all_names = set(self._scenes.keys()) | set(self._factories.keys())
        return sorted(all_names)

    def register(self, name: str, factory: Callable[[], Scene]) -> None:
        """Register *factory* — a zero-arg callable returning a ``Scene`` — for *name*.

        This is a test-only escape hatch for injecting in-memory scenes without
        any JSON on disk.
        """
        self._factories[name] = factory


class _SceneStackEntry:
    """One entry in ``SceneManager``'s scene stack.  Internal use only.

    ``saved_merge`` is the merge-strategy snapshot to restore via
    ``EffectAdmin.apply_merge_strategies`` when this entry is popped — ``None``
    for the base entry a ``load`` creates (nothing to restore), and the
    captured live map for an entry pushed by ``overlay``.  Folding the
    snapshot into the same entry as the scene stack means the two stacks
    can never desync.
    """

    __slots__ = ("rules", "saved_merge", "scene", "state")

    def __init__(
        self,
        scene: Scene,
        state: GameState,
        rules: list[GameRule],
        saved_merge: dict[str, MergeStrategy] | None,
    ) -> None:
        self.scene = scene
        self.state = state
        self.rules = rules
        self.saved_merge = saved_merge


class SceneManager(SceneControls):
    """Manages a stack of active scenes, driving the game engine each tick.

    Construction::

        manager = SceneManager(engine, effect_registry, rule_registry, scene_registry, effect_admin)

    Driving the game loop::

        while running:
            manager.update()

    Scene transitions (``load``, ``overlay``, ``pop``) are deferred: they
    record a pending transition and the last call per tick wins.  The
    transition executes at the end of ``update()`` after ``engine.update``
    has processed all queued events.

    Scene lookup delegates entirely to *scene_registry*: ``load`` and
    ``overlay`` call ``scene_registry.get(name)``; ``load`` raises
    ``ValueError`` for unknown names because ``SceneRegistry.get`` does.

    *effect_admin* is the scene-transition face of the same effect system
    ``engine`` was built with (its ``EffectControls`` and ``EffectAdmin`` are
    two faces of one ``EffectManager`` instance, mirroring the
    ``NetworkControls``/``TransmitPump`` split). Every local-effects push and
    merge-strategy reset/capture/apply routes through *effect_admin*, never
    through a stack entry's ``state.effect_controls``.
    """

    __slots__ = (
        "_effect_admin",
        "_effect_registry",
        "_engine",
        "_pending",
        "_rule_registry",
        "_scene_registry",
        "_stack",
    )

    def __init__(
        self,
        engine: GameEngine,
        effect_registry: PackRegistry,
        rule_registry: PackRegistry,
        scene_registry: SceneRegistry,
        effect_admin: EffectAdmin,
    ) -> None:
        self._engine = engine
        self._effect_registry = effect_registry
        self._rule_registry = rule_registry
        self._scene_registry = scene_registry
        self._effect_admin = effect_admin
        self._stack: list[_SceneStackEntry] = []
        self._pending: (
            tuple[Literal["load"], Scene]
            | tuple[Literal["overlay"], Scene]
            | tuple[Literal["pop"]]
            | None
        ) = None

    # ------------------------------------------------------------------
    # SceneControls interface — deferred transitions
    # ------------------------------------------------------------------

    def load(self, name: str) -> None:
        """Record a load transition for *name*; raises immediately if unknown or packs invalid."""
        scene = self._scene_registry.get(name)
        self._validate_packs(scene)
        self._pending = ("load", scene)

    def overlay(self, name: str) -> None:
        """Record an overlay transition for *name*; raises immediately if invalid."""
        if not self._stack:
            raise ValueError("Cannot overlay: no active scene on stack")
        scene = self._scene_registry.get(name)
        self._validate_packs(scene)
        self._pending = ("overlay", scene)

    @property
    def active_state(self) -> GameState | None:
        """The ``GameState`` for the top-most active scene, or ``None`` if the stack is empty."""
        if not self._stack:
            return None
        return self._stack[-1].state

    def pop(self) -> None:
        """Record a pop transition; raises immediately if stack has ≤ 1 entry."""
        n = len(self._stack)
        if n <= 1:
            raise ValueError(f"Cannot pop: stack has {n} entr{'y' if n == 1 else 'ies'}")
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
            self._engine.update(self._stack[-1].state)

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
        """Return combined rules: shared-pack items first, scene-local items after."""
        combined = []
        for pack_name, _ in scene.rule_packs:
            for item_name in self._rule_registry.items(pack_name):
                combined.append(self._rule_registry.get(pack_name, item_name, GameRule))
        for item_name in scene.local_rule_registry.items():
            combined.append(scene.local_rule_registry.get(item_name, GameRule))
        return combined

    def _deactivate(self, entry: _SceneStackEntry) -> None:
        entry.state.effect_controls.stop_effect(Scope.ALL)
        entry.state.clear_queue()

    def _activate(self, entry: _SceneStackEntry) -> None:
        self._engine.set_rules(entry.rules)
        entry.state.clear_queue()
        self._effect_admin.set_local_effects(entry.scene.local_effect_registry)

    def _do_load(self, scene: Scene) -> None:
        """Replace the entire stack with a single fresh entry for *scene*."""
        combined_rules = self._resolve_rules(scene)

        for i in range(len(self._stack) - 1, -1, -1):
            self._deactivate(self._stack[i])

        self._stack = []
        state = self._engine.create_state(self, scene.initial_data)
        entry = _SceneStackEntry(scene, state, combined_rules, saved_merge=None)
        self._stack.append(entry)
        self._effect_admin.reset_merge_strategies()
        self._activate(entry)

    def _do_overlay(self, scene: Scene) -> None:
        """Suspend the current top and push *scene* above it."""
        combined_rules = self._resolve_rules(scene)

        self._deactivate(self._stack[-1])
        saved_merge = self._effect_admin.capture_merge_strategies()

        state = self._engine.create_state(self, scene.initial_data)
        entry = _SceneStackEntry(scene, state, combined_rules, saved_merge=saved_merge)
        self._stack.append(entry)
        self._activate(entry)

    def _do_pop(self) -> None:
        """Remove the top entry and restore the entry below it."""
        self._deactivate(self._stack[-1])
        popped = self._stack.pop()
        # pop() rejects a stack of size <= 1, so the popped entry is always one
        # overlay() pushed — never the base entry from load(), whose
        # saved_merge is None. Narrows the type for apply_merge_strategies.
        assert popped.saved_merge is not None
        self._effect_admin.apply_merge_strategies(popped.saved_merge)

        self._activate(self._stack[-1])
