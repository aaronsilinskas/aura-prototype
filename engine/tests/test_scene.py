"""Tests for engine.scene: Scene, SceneControls, and SceneManager."""

from __future__ import annotations

import sys

import pytest

from engine.engine import GameEngine, GameRule
from engine.events import Event, EventGroup
from engine.packs import PackRegistry, _PackEntry
from engine.scene import Scene, SceneManager
from engine.state import EffectControls, GameState, SceneControls
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_GROUP = EventGroup("test")

MODULE_PREFIX = "tp_scene"


@pytest.fixture()
def pack_env(tmp_path):
    """Yield a packs root directory; insert into sys.path and clean up after."""
    packs_root = tmp_path / MODULE_PREFIX
    packs_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known_modules = set(sys.modules)
    yield packs_root
    for key in list(sys.modules):
        if key not in known_modules:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_rule_pack(root, pack_name: str, version: str, items: dict[str, str]) -> None:
    """Create a rule pack directory with RULE-exporting items under *root*."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text(version + "\n")
    for item_name, content in items.items():
        (pack_dir / (item_name + ".py")).write_text(content)


def _make_effect_pack(root, pack_name: str, version: str) -> None:
    """Create a minimal effect pack directory with only version.txt."""
    pack_dir = root / pack_name
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "version.txt").write_text(version + "\n")


def _make_registries(pack_env_path: str):
    """Return (effect_registry, rule_registry) scanned from *pack_env_path*."""
    effect_registry = PackRegistry(item_attr="BUILD")
    rule_registry = _TestPackRegistry(item_attr="RULE")
    effect_registry.scan_dir(pack_env_path, MODULE_PREFIX)
    rule_registry.scan_dir(pack_env_path, MODULE_PREFIX)
    return effect_registry, rule_registry


def _make_engine() -> GameEngine:
    return GameEngine(effect_controls=EffectControls())


class _TestPackRegistry(PackRegistry):
    """PackRegistry subclass that supports registering pre-built instances for testing."""

    def register_instance(
        self, pack_name: str, item_name: str, instance: object, version: str = "1.0"
    ) -> None:
        if pack_name not in self._packs:
            self._packs[pack_name] = _PackEntry(
                name=pack_name,
                version=Version.parse(version),
                module_prefix="",
                item_names={item_name},
                source_path="",
            )
        else:
            self._packs[pack_name].item_names.add(item_name)
        self._cache[(pack_name, item_name)] = instance


def _scene_factory(**kwargs):
    """Return a zero-arg factory producing a Scene from keyword overrides."""

    def factory():
        return Scene(
            effect_packs=kwargs.get("effect_packs", []),
            rule_packs=kwargs.get("rule_packs", []),
            initial_data=kwargs.get("initial_data"),
            on_load=kwargs.get("on_load"),
            on_unload=kwargs.get("on_unload"),
            on_suspend=kwargs.get("on_suspend"),
            on_resume=kwargs.get("on_resume"),
        )

    return factory


def _rule(name: str = "test.rule") -> GameRule:
    return GameRule()


# ---------------------------------------------------------------------------
# SceneControls — abstract base
# ---------------------------------------------------------------------------


def test_scene_controls_load_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.load("any")


def test_scene_controls_overlay_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.overlay("any")


def test_scene_controls_pop_raises_not_implemented_error() -> None:
    sc = SceneControls()

    with pytest.raises(NotImplementedError):
        sc.pop()


# ---------------------------------------------------------------------------
# Scene — declarative data bundle
# ---------------------------------------------------------------------------


def test_scene_effect_packs_accessible_after_construction() -> None:
    effect_packs = [("fx", "1.0")]
    scene = Scene(effect_packs=effect_packs, rule_packs=[])

    assert scene.effect_packs is effect_packs


def test_scene_rule_packs_accessible_after_construction() -> None:
    rule_packs = [("rules", "2.0")]
    scene = Scene(effect_packs=[], rule_packs=rule_packs)

    assert scene.rule_packs is rule_packs


def test_scene_initial_data_defaults_to_none() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.initial_data is None


def test_scene_initial_data_accessible_when_provided() -> None:
    data = {"score": 0}
    scene = Scene(effect_packs=[], rule_packs=[], initial_data=data)

    assert scene.initial_data is data


def test_scene_lifecycle_callbacks_default_to_none() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.on_load is None
    assert scene.on_unload is None
    assert scene.on_suspend is None
    assert scene.on_resume is None


def test_scene_lifecycle_callbacks_accessible_when_provided() -> None:
    def cb(ec: object) -> None:
        pass

    scene = Scene(
        effect_packs=[],
        rule_packs=[],
        on_load=cb,
        on_unload=cb,
        on_suspend=cb,
        on_resume=cb,
    )

    assert scene.on_load is cb
    assert scene.on_unload is cb
    assert scene.on_suspend is cb
    assert scene.on_resume is cb


def test_scene_rejects_unknown_attributes() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    with pytest.raises(AttributeError):
        scene.runtime_state = "mutable"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# SceneManager — registration
# ---------------------------------------------------------------------------


def test_scene_manager_satisfies_scene_controls_interface() -> None:
    engine = _make_engine()
    effect_registry = PackRegistry(item_attr="BUILD")
    rule_registry = PackRegistry(item_attr="RULE")

    manager = SceneManager(engine, effect_registry, rule_registry)

    assert isinstance(manager, SceneControls)


def test_load_succeeds_after_register() -> None:
    engine = _make_engine()
    effect_registry = PackRegistry(item_attr="BUILD")
    rule_registry = PackRegistry(item_attr="RULE")
    manager = SceneManager(engine, effect_registry, rule_registry)
    factory = _scene_factory()

    manager.register("main", factory)
    manager.load("main")
    manager.update()  # should not raise


def test_register_overwrites_existing_factory_silently() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    loaded = []

    manager.register("main", _scene_factory(on_load=lambda ec: loaded.append("first")))
    manager.register("main", _scene_factory(on_load=lambda ec: loaded.append("second")))
    manager.load("main")
    manager.update()

    assert loaded == ["second"]


# ---------------------------------------------------------------------------
# SceneManager — active_state
# ---------------------------------------------------------------------------


def test_active_state_is_none_before_any_scene_is_loaded() -> None:
    manager = SceneManager(
        _make_engine(), PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE")
    )

    assert manager.active_state is None


def test_active_state_returns_game_state_after_scene_loads() -> None:
    manager = SceneManager(
        _make_engine(), PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE")
    )
    manager.register("main", _scene_factory())
    manager.load("main")
    manager.update()

    assert isinstance(manager.active_state, GameState)


def test_active_state_is_none_while_load_is_pending_but_not_yet_applied() -> None:
    manager = SceneManager(
        _make_engine(), PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE")
    )
    manager.register("main", _scene_factory())
    manager.load("main")

    # Transition is recorded but update() has not been called yet
    assert manager.active_state is None


def test_active_state_changes_after_load_replaces_scene() -> None:
    manager = SceneManager(
        _make_engine(), PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE")
    )
    manager.register("first", _scene_factory())
    manager.register("second", _scene_factory())

    manager.load("first")
    manager.update()
    first_state = manager.active_state

    manager.load("second")
    manager.update()

    assert manager.active_state is not first_state


# ---------------------------------------------------------------------------
# SceneManager — immediate validation (ValueError raised before any state change)
# ---------------------------------------------------------------------------


def test_load_raises_immediately_for_unregistered_scene_name() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.load("nonexistent")


def test_overlay_raises_immediately_for_unregistered_scene_name() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    with pytest.raises(ValueError, match="Unknown scene"):
        manager.overlay("nonexistent")


def test_overlay_raises_immediately_when_stack_is_empty() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("overlay_scene", _scene_factory())

    with pytest.raises(ValueError):
        manager.overlay("overlay_scene")


def test_pop_raises_immediately_with_zero_entries_on_stack() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    with pytest.raises(ValueError):
        manager.pop()


def test_pop_raises_immediately_with_exactly_one_entry_on_stack() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("main", _scene_factory())
    manager.load("main")
    manager.update()  # apply the load

    with pytest.raises(ValueError):
        manager.pop()


# ---------------------------------------------------------------------------
# SceneManager — pack version validation on load()
# ---------------------------------------------------------------------------


def test_load_validates_effect_pack_version_before_any_lifecycle_callback(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    manager = SceneManager(engine, effect_registry, rule_registry)

    on_load_called = []
    manager.register(
        "main",
        _scene_factory(
            effect_packs=[("fx", "99.0")],  # incompatible major version
            on_load=lambda ec: on_load_called.append(True),
        ),
    )
    with pytest.raises(ValueError):
        manager.load("main")

    assert on_load_called == [], "on_load must not fire when pack validation fails"


def test_load_leaves_stack_untouched_when_pack_version_is_incompatible(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    manager = SceneManager(engine, effect_registry, rule_registry)

    # Load a valid initial scene first
    manager.register("initial", _scene_factory())
    manager.load("initial")
    manager.update()

    # Attempt to load a scene with incompatible effect pack
    manager.register("bad", _scene_factory(effect_packs=[("fx", "99.0")]))
    with pytest.raises(ValueError):
        manager.load("bad")

    # Manager should still be usable; loading initial again works
    manager.load("initial")
    manager.update()  # no error


def test_load_validates_rule_pack_version_before_any_lifecycle_callback(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    manager = SceneManager(engine, effect_registry, rule_registry)

    on_load_called = []
    manager.register(
        "main",
        _scene_factory(
            rule_packs=[("rules", "99.0")],  # incompatible major version
            on_load=lambda ec: on_load_called.append(True),
        ),
    )
    with pytest.raises(ValueError):
        manager.load("main")

    assert on_load_called == []


# ---------------------------------------------------------------------------
# SceneManager — pack version validation on overlay()
# ---------------------------------------------------------------------------


def test_overlay_validates_packs_before_suspending_active_scene(pack_env) -> None:
    _make_effect_pack(pack_env, "fx", "1.0")
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _make_engine()
    manager = SceneManager(engine, effect_registry, rule_registry)

    on_suspend_called = []
    manager.register("main", _scene_factory(on_suspend=lambda ec: on_suspend_called.append(True)))
    manager.load("main")
    manager.update()

    manager.register("overlay_scene", _scene_factory(effect_packs=[("fx", "99.0")]))
    with pytest.raises(ValueError):
        manager.overlay("overlay_scene")

    assert on_suspend_called == [], "on_suspend must not fire when overlay pack validation fails"


# ---------------------------------------------------------------------------
# SceneManager — update() engine delegation and deferred transitions
# ---------------------------------------------------------------------------


def test_update_skips_engine_update_when_stack_is_empty() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    # No exception should be raised; engine.update would fail without a state
    manager.update()


def test_update_calls_engine_update_with_active_state_on_each_tick() -> None:
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("main", _scene_factory())
    manager.load("main")
    manager.update()  # stack empty at start of tick; engine.update skipped; load fires

    assert engine._update_calls == [], "engine.update must be skipped when stack is empty"

    manager.update()  # stack now has one entry; engine.update fires
    assert len(engine._update_calls) == 1

    manager.update()  # another tick; same active state passed each time
    assert len(engine._update_calls) == 2
    assert engine._update_calls[0] is engine._update_calls[1]


class _TrackingEngine(GameEngine):
    """GameEngine subclass that records each update() call for order verification."""

    def __init__(self, effect_controls: EffectControls) -> None:
        super().__init__(effect_controls=effect_controls)
        self._update_calls: list = []

    @property
    def _last_state(self) -> GameState:
        return self._update_calls[-1]

    def update(self, state: GameState) -> None:
        self._update_calls.append(state)
        super().update(state)


def test_on_load_fires_after_engine_update_in_same_tick() -> None:
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    on_load_called = []

    manager.register("main", _scene_factory(on_load=lambda ec: on_load_called.append("on_load")))
    manager.load("main")
    manager.update()

    # First update: stack was empty so engine.update skipped; on_load fires
    assert engine._update_calls == [], "engine.update must be skipped when stack is empty"
    assert on_load_called == ["on_load"]

    # Second update: stack has one entry, engine.update fires; then pending load executes
    on_load_called.clear()
    engine._update_calls.clear()
    manager.load("main")
    manager.update()

    assert len(engine._update_calls) == 1, "engine.update must run before the transition"
    assert on_load_called == ["on_load"], "on_load fires after engine.update within the same tick"


def test_last_pending_transition_wins_within_one_tick() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    loaded = []

    manager.register("scene_a", _scene_factory(on_load=lambda ec: loaded.append("a")))
    manager.register("scene_b", _scene_factory(on_load=lambda ec: loaded.append("b")))

    # Both recorded in one tick — last wins
    manager.load("scene_a")
    manager.load("scene_b")
    manager.update()

    assert loaded == ["b"], "last load() call in tick should win"


def test_overlay_wins_when_load_and_overlay_both_called_in_same_tick() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    unloaded = []
    suspended = []
    manager.register(
        "base",
        _scene_factory(
            on_unload=lambda ec: unloaded.append("base"),
            on_suspend=lambda ec: suspended.append("base"),
        ),
    )
    manager.register("new", _scene_factory())
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()

    # In the same tick: load first, then overlay — overlay (last call) wins.
    # overlay suspends base rather than unloading it; load would have unloaded it.
    manager.load("new")
    manager.overlay("overlay_scene")
    manager.update()

    assert suspended == ["base"], "overlay() called last must win — base is suspended not unloaded"
    assert unloaded == [], "load() called first must be superseded"


# ---------------------------------------------------------------------------
# SceneManager — load() lifecycle
# ---------------------------------------------------------------------------


def test_load_passes_scene_manager_as_scene_controls_in_active_state() -> None:
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("main", _scene_factory())
    manager.load("main")
    manager.update()  # load fires; state created
    manager.update()  # engine.update(active_state)

    assert engine._last_state.scene_controls is manager


def test_load_seeds_active_state_data_from_scene_initial_data() -> None:
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("main", _scene_factory(initial_data={"level": 5}))
    manager.load("main")
    manager.update()  # load fires; state created with initial_data
    manager.update()  # engine.update(active_state); _last_state is now set

    assert engine._last_state.get("level", None) == 5


def test_on_load_callback_receives_effect_controls() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    received_ec = []
    manager.register("main", _scene_factory(on_load=lambda ec: received_ec.append(ec)))
    manager.load("main")
    manager.update()

    assert len(received_ec) == 1
    assert isinstance(received_ec[0], EffectControls)


def test_on_unload_callback_receives_effect_controls() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    received = []
    manager.register("main", _scene_factory(on_unload=lambda ec: received.append(ec)))
    manager.register("next", _scene_factory())
    manager.load("main")
    manager.update()
    manager.load("next")
    manager.update()

    assert len(received) == 1
    assert isinstance(received[0], EffectControls)


def test_on_suspend_callback_receives_effect_controls() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    received = []
    manager.register("main", _scene_factory(on_suspend=lambda ec: received.append(ec)))
    manager.register("overlay_scene", _scene_factory())
    manager.load("main")
    manager.update()
    manager.overlay("overlay_scene")
    manager.update()

    assert len(received) == 1
    assert isinstance(received[0], EffectControls)


def test_on_resume_callback_receives_effect_controls() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    received = []
    manager.register("main", _scene_factory(on_resume=lambda ec: received.append(ec)))
    manager.register("overlay_scene", _scene_factory())
    manager.load("main")
    manager.update()
    manager.overlay("overlay_scene")
    manager.update()
    manager.pop()
    manager.update()

    assert len(received) == 1
    assert isinstance(received[0], EffectControls)


def test_load_does_not_require_on_load_callback() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    manager.register("main", _scene_factory())  # on_load=None
    manager.load("main")
    manager.update()  # must not raise


def test_load_fires_on_unload_top_down_on_all_stack_entries() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    unload_order = []

    manager.register("base", _scene_factory(on_unload=lambda ec: unload_order.append("base")))
    manager.register("top", _scene_factory(on_unload=lambda ec: unload_order.append("top")))
    manager.register("new", _scene_factory())

    # Load base, then overlay top so stack has two entries
    manager.load("base")
    manager.update()
    manager.overlay("top")
    manager.update()

    # Now load "new" — should unload top then base (top-down order)
    manager.load("new")
    manager.update()

    assert unload_order == ["top", "base"]


def test_load_clears_suspended_state_queues_so_stale_events_do_not_outlive_the_stack() -> None:
    engine = _TrackingEngine(EffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), rule_registry)
    base_events = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    manager.register("base", _scene_factory(rule_packs=[("stubs", "1.0")]))
    manager.register("overlay_scene", _scene_factory())
    manager.register("new", _scene_factory())

    # Build a 2-layer stack
    manager.load("base")
    manager.update()
    manager.update()  # tick; engine._last_state = base_state
    base_state = engine._last_state

    manager.overlay("overlay_scene")
    manager.update()  # overlay fires; base_state.clear_queue() called

    # Queue a stale event on the now-suspended base_state
    base_state.queue_event(Event(_GROUP, "stale"))

    # load("new") clears queues on all outgoing states (including suspended base_state)
    manager.load("new")
    manager.update()  # engine.update(overlay_state), then _do_load clears base_state

    # "stale" was on base_state, which is now discarded; base_rule is no longer in engine
    # and base_state is gone. Verify no base events beyond the clear.
    assert "stale" not in base_events


def test_load_dispatches_events_to_scene_rules_on_following_ticks(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    fired: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired.append("scene")

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    manager.register("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    manager.load("main")
    manager.update()  # load fires; state created
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired, "scene rule must receive events after load"
    assert "pack" in fired, "pack rule must receive events after load"


def test_scene_rules_fire_before_pack_rules(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    fired: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired.append("scene")

    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule.on(Event, lambda e, s: fired.append("pack"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    manager.register("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    manager.load("main")
    manager.update()
    manager.update()

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert fired.index("scene") < fired.index("pack")


# ---------------------------------------------------------------------------
# SceneManager — overlay() lifecycle
# ---------------------------------------------------------------------------


def test_overlay_suspends_active_scene_and_pushes_without_clearing_stack() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    suspended = []
    manager.register("base", _scene_factory(on_suspend=lambda ec: suspended.append("base")))
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()

    manager.overlay("overlay_scene")
    manager.update()

    assert suspended == ["base"]


def test_overlay_clears_suspended_base_state_queue_before_pushing() -> None:
    engine = _TrackingEngine(EffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), rule_registry)
    base_events = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    manager.register("base", _scene_factory(rule_packs=[("stubs", "1.0")]))
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()
    manager.update()  # engine.update(base_state)
    base_state = engine._last_state

    # Queue a stale event, then overlay (which clears the base_state queue)
    base_state.queue_event(Event(_GROUP, "stale"))
    manager.overlay("overlay_scene")
    manager.update()  # engine.update on base, then overlay fires + clears base_state queue

    # After overlay, queue another event on the suspended base_state externally
    base_state.queue_event(Event(_GROUP, "while_suspended"))
    manager.pop()
    manager.update()  # pop fires: defensive clear_queue on base_state, then on_resume
    manager.update()  # engine.update(base_state); "while_suspended" must have been cleared

    assert "while_suspended" not in base_events, (
        "event queued while suspended must not replay after pop"
    )


# ---------------------------------------------------------------------------
# SceneManager — pop() lifecycle
# ---------------------------------------------------------------------------


def test_pop_fires_lifecycle_callbacks_in_correct_order() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    lifecycle = []

    manager.register("base", _scene_factory(on_resume=lambda ec: lifecycle.append("base_resume")))
    manager.register(
        "overlay_scene", _scene_factory(on_unload=lambda ec: lifecycle.append("overlay_unload"))
    )

    manager.load("base")
    manager.update()
    manager.overlay("overlay_scene")
    manager.update()

    manager.pop()
    manager.update()

    assert lifecycle == ["overlay_unload", "base_resume"]


def test_pop_restores_base_scene_rules_so_events_dispatch_to_base_rules(pack_env) -> None:
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {"rule_a": ("from engine.engine import GameRule\nRULE = GameRule()\n")},
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    base_events: list = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    pack_rule = rule_registry.get("rules", "rule_a", GameRule)
    pack_events: list = []
    pack_rule.on(Event, lambda e, s: pack_events.append(e.name))

    manager.register("base", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()  # load fires; stack empty at start so engine.update skipped
    manager.update()  # tick on base; _last_state = base_state
    manager.overlay("overlay_scene")
    manager.update()  # engine.update(base_state), then overlay fires
    manager.pop()
    manager.update()  # engine.update(overlay_state), then pop fires; base rules restored
    manager.update()  # engine.update(base_state); _last_state = base_state

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "verify" in base_events, "base_rule must receive events after pop restores base scene"
    assert "verify" in pack_events, "pack_rule must receive events after pop restores base scene"


def test_pop_clears_restored_state_queue_so_suspended_events_do_not_replay() -> None:
    engine = _TrackingEngine(EffectControls())
    rule_registry = _TestPackRegistry(item_attr="RULE")
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), rule_registry)
    base_events: list = []

    class _BaseRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            base_events.append(event.name)

    base_rule = _BaseRule()
    rule_registry.register_instance("stubs", "base_rule", base_rule)
    manager.register("base", _scene_factory(rule_packs=[("stubs", "1.0")]))
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()
    manager.update()  # engine.update(base_state); _last_state = base_state
    base_state = engine._last_state

    manager.overlay("overlay_scene")
    manager.update()  # overlay fires; base_state.clear_queue() called

    # Directly queue a stale event on the suspended base_state
    base_state.queue_event(Event(_GROUP, "stale_while_suspended"))

    manager.pop()
    manager.update()  # pop fires: defensive clear_queue on base_state before on_resume
    manager.update()  # engine.update(base_state) — stale event must not fire

    assert "stale_while_suspended" not in base_events, (
        "events queued on suspended state must be discarded by pop's defensive clear_queue"
    )


def test_pop_restores_scene_below_in_deep_overlay_stack() -> None:
    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))
    resumed = []
    manager.register("base", _scene_factory(on_resume=lambda ec: resumed.append("base")))
    manager.register("mid", _scene_factory(on_resume=lambda ec: resumed.append("mid")))
    manager.register("top", _scene_factory())

    manager.load("base")
    manager.update()
    manager.overlay("mid")
    manager.update()
    manager.overlay("top")
    manager.update()

    manager.pop()
    manager.update()

    assert resumed == ["mid"], "pop from 3-layer stack must resume the scene directly below"

    manager.pop()
    manager.update()

    assert resumed == ["mid", "base"]


# ---------------------------------------------------------------------------
# SceneManager — rule pack integration
# ---------------------------------------------------------------------------


def test_rule_pack_items_all_receive_events_after_load(pack_env) -> None:
    rule_content = "from engine.engine import GameRule\nRULE = GameRule()\n"
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {
            "rule_a": rule_content,
            "rule_b": rule_content,
        },
    )
    effect_registry, rule_registry = _make_registries(str(pack_env))
    engine = _TrackingEngine(EffectControls())
    manager = SceneManager(engine, effect_registry, rule_registry)

    fired_by: list = []

    class _SceneRule(GameRule):
        def handle_event(self, event: Event, state: GameState) -> None:
            fired_by.append("scene")

    pack_rule_a = rule_registry.get("rules", "rule_a", GameRule)
    pack_rule_b = rule_registry.get("rules", "rule_b", GameRule)
    pack_rule_a.on(Event, lambda e, s: fired_by.append("pack_a"))
    pack_rule_b.on(Event, lambda e, s: fired_by.append("pack_b"))

    scene_r = _SceneRule()
    rule_registry.register_instance("stubs", "scene_rule", scene_r)
    manager.register("main", _scene_factory(rule_packs=[("stubs", "1.0"), ("rules", "1.0")]))
    manager.load("main")
    manager.update()  # load fires
    manager.update()  # engine.update(active_state)

    engine._last_state.queue_event(Event(_GROUP, "verify"))
    manager.update()

    assert "scene" in fired_by, "scene rule must fire"
    assert "pack_a" in fired_by, "pack rule_a must fire"
    assert "pack_b" in fired_by, "pack rule_b must fire"


def test_rule_pack_items_loaded_in_alphabetical_order(pack_env) -> None:
    rule_template = (
        "from engine.engine import GameRule\nimport engine.scene as _s\nRULE = GameRule()\n"
    )
    _make_rule_pack(
        pack_env,
        "rules",
        "1.0",
        {
            "z_rule": rule_template,
            "a_rule": rule_template,
            "m_rule": rule_template,
        },
    )
    _effect_registry, rule_registry = _make_registries(str(pack_env))

    # Verify items() returns alphabetical order
    items = rule_registry.items("rules")
    assert items == sorted(items)


# ---------------------------------------------------------------------------
# SceneManager — GC eligibility after full unload
# ---------------------------------------------------------------------------


def test_unloaded_scene_is_not_retained_by_manager() -> None:
    import gc
    import weakref

    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    created_scene = None

    def factory():
        nonlocal created_scene
        created_scene = Scene(effect_packs=[], rule_packs=[])
        return created_scene

    manager.register("main", factory)
    manager.load("main")
    manager.update()

    ref = weakref.ref(created_scene)
    created_scene = None  # drop local reference

    # Now load a different scene to trigger unload of "main"
    manager.register("other", _scene_factory())
    manager.load("other")
    manager.update()

    gc.collect()
    assert ref() is None, "Scene should be GC-eligible after full unload"


def test_suspended_scene_remains_on_stack_after_overlay() -> None:
    import gc
    import weakref

    engine = _make_engine()
    manager = SceneManager(engine, PackRegistry(item_attr="BUILD"), PackRegistry(item_attr="RULE"))

    created_scene = None

    def factory():
        nonlocal created_scene
        created_scene = Scene(effect_packs=[], rule_packs=[])
        return created_scene

    manager.register("base", factory)
    manager.register("overlay_scene", _scene_factory())

    manager.load("base")
    manager.update()

    ref = weakref.ref(created_scene)
    created_scene = None

    manager.overlay("overlay_scene")
    manager.update()

    gc.collect()
    assert ref() is not None, "Suspended scene should remain on stack (not GC'd)"
