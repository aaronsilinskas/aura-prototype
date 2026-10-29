"""Tests for engine.scene.SceneRegistry lookups and the Scene.version / ir_codec fields.

Scanned registries come from ``scan_pack_roots`` over trees laid out by the
shared ``pack_tree`` builder; scan failures are covered by the catalog tests.
"""

from __future__ import annotations

import pytest

from engine.pack_catalog import scan_pack_roots
from engine.scene import Scene, SceneRegistry
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scan_scene(pack_tree, name: str = "forest", **scene_fields) -> SceneRegistry:
    """Scan a root holding the single scene *name*; return the catalog's ``SceneRegistry``."""
    return pack_tree.scan(scenes={name: scene_fields}).scene_registry


# ---------------------------------------------------------------------------
# Scene.version field
# ---------------------------------------------------------------------------


def test_scene_version_is_stored_as_the_version_passed_to_constructor() -> None:
    v = Version(1, 2)
    scene = Scene(effect_packs=[], rule_packs=[], version=v)

    assert scene.version is v


def test_scene_version_defaults_to_none_when_not_provided() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.version is None


# ---------------------------------------------------------------------------
# Scene.ir_codec field
# ---------------------------------------------------------------------------


def test_scene_ir_codec_defaults_to_aura_when_not_provided() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.ir_codec == "aura"


def test_scene_ir_codec_is_stored_as_the_value_passed_to_constructor() -> None:
    scene = Scene(effect_packs=[], rule_packs=[], ir_codec="tag")

    assert scene.ir_codec == "tag"


# ---------------------------------------------------------------------------
# SceneRegistry — construction
# ---------------------------------------------------------------------------


def test_scene_registry_names_is_empty_on_construction() -> None:
    registry = SceneRegistry()

    assert registry.names() == []


# ---------------------------------------------------------------------------
# SceneRegistry.get — correct data returned
# ---------------------------------------------------------------------------


def test_get_returns_scene_with_version_parsed_from_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree, version="2.3")

    scene = registry.get("forest")

    assert scene.version.major == 2
    assert scene.version.minor == 3


def test_get_returns_scene_with_effect_packs_from_json(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.effect_pack(root, "fx")
    pack_tree.scene(root, "forest", effect_packs=[["fx", "1.0"]])
    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")

    assert scene.effect_packs == [["fx", "1.0"]]


def test_get_returns_scene_with_rule_packs_from_json(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.rule_pack(root, "rules")
    pack_tree.scene(root, "forest", rule_packs=[["rules", "1.0"]])
    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")

    assert scene.rule_packs == [["rules", "1.0"]]


def test_get_returns_scene_with_initial_data_from_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree, initial_data={"score": 0, "level": 5})

    scene = registry.get("forest")

    assert scene.initial_data == {"score": 0, "level": 5}


def test_get_returns_scene_with_none_initial_data_when_not_in_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    scene = registry.get("forest")

    assert scene.initial_data is None


def test_get_returns_scene_with_default_ir_codec_when_not_in_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    scene = registry.get("forest")

    assert scene.ir_codec == "aura"


def test_get_returns_scene_with_ir_codec_parsed_from_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree, ir_codec="tag")

    scene = registry.get("forest")

    assert scene.ir_codec == "tag"


# ---------------------------------------------------------------------------
# SceneRegistry.get — fresh instance per call
# ---------------------------------------------------------------------------


def test_get_returns_fresh_scene_on_each_call(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a is not scene_b


def test_get_returns_scenes_with_shared_version_instance(pack_tree) -> None:
    registry = _scan_scene(pack_tree, version="1.0")

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a.version is scene_b.version


def test_get_returns_fresh_initial_data_so_mutation_does_not_affect_next_call(
    pack_tree,
) -> None:
    registry = _scan_scene(pack_tree, initial_data={"score": 0})

    scene_a = registry.get("forest")
    scene_a.initial_data["score"] = 99

    scene_b = registry.get("forest")
    assert scene_b.initial_data["score"] == 0


# ---------------------------------------------------------------------------
# SceneRegistry.get — unknown name
# ---------------------------------------------------------------------------


def test_get_raises_value_error_for_unknown_scene_name() -> None:
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="Unknown scene"):
        registry.get("nonexistent")


# ---------------------------------------------------------------------------
# SceneRegistry.resolve_known — known-scene check
# ---------------------------------------------------------------------------


def test_resolve_known_returns_a_scanned_scene_name(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    assert registry.resolve_known("forest") == "forest"


def test_resolve_known_returns_a_factory_registered_scene_name() -> None:
    registry = SceneRegistry()
    registry.register("in_memory", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert registry.resolve_known("in_memory") == "in_memory"


def test_resolve_known_raises_value_error_naming_the_known_scenes(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": {}, "cave": {}}).scene_registry

    with pytest.raises(ValueError, match=r"'nowhere'.*cave, forest"):
        registry.resolve_known("nowhere")


# ---------------------------------------------------------------------------
# SceneRegistry.ir_codec_for — lightweight accessor
# ---------------------------------------------------------------------------


def test_ir_codec_for_returns_the_declared_codec_name(pack_tree) -> None:
    registry = _scan_scene(pack_tree, "arena", ir_codec="tag")

    assert registry.ir_codec_for("arena") == "tag"


def test_ir_codec_for_raises_value_error_for_unknown_scene_name() -> None:
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="Unknown scene"):
        registry.ir_codec_for("nonexistent")


def test_ir_codec_for_works_for_register_factory_scene() -> None:
    registry = SceneRegistry()
    registry.register(
        "in_memory",
        lambda: Scene(effect_packs=[], rule_packs=[], ir_codec="tag"),
    )

    assert registry.ir_codec_for("in_memory") == "tag"


def test_ir_codec_for_prefers_factory_override_over_scanned_scene(pack_tree) -> None:
    registry = _scan_scene(pack_tree, ir_codec="tag")
    registry.register(
        "forest",
        lambda: Scene(effect_packs=[], rule_packs=[], ir_codec="aura"),
    )

    assert registry.ir_codec_for("forest") == "aura"


# ---------------------------------------------------------------------------
# SceneRegistry.names — sorted order
# ---------------------------------------------------------------------------


def test_names_returns_scene_names_sorted_alphabetically(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"zebra": {}, "alpha": {}, "mango": {}}).scene_registry

    assert registry.names() == ["alpha", "mango", "zebra"]


# ---------------------------------------------------------------------------
# SceneRegistry.register — in-memory escape hatch
# ---------------------------------------------------------------------------


def test_register_factory_allows_get_without_any_disk_scan() -> None:
    registry = SceneRegistry()
    v = Version(1, 0)
    registry.register("in_memory", lambda: Scene(effect_packs=[], rule_packs=[], version=v))

    scene = registry.get("in_memory")

    assert scene.version is v


def test_register_factory_scene_appears_in_names() -> None:
    registry = SceneRegistry()
    registry.register("in_memory", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert "in_memory" in registry.names()


def test_register_factory_returns_fresh_scene_on_each_get() -> None:
    registry = SceneRegistry()
    registry.register("in_memory", lambda: Scene(effect_packs=[], rule_packs=[]))

    scene_a = registry.get("in_memory")
    scene_b = registry.get("in_memory")

    assert scene_a is not scene_b


def test_register_factory_scene_exposes_same_version_field_as_json_scene(
    pack_tree,
) -> None:
    registry = _scan_scene(pack_tree, "from_disk", version="1.0")
    registry.register(
        "from_memory",
        lambda: Scene(effect_packs=[], rule_packs=[], version=Version(1, 0)),
    )

    disk_scene = registry.get("from_disk")
    mem_scene = registry.get("from_memory")

    assert disk_scene.version.major == mem_scene.version.major
    assert disk_scene.version.minor == mem_scene.version.minor


def test_names_does_not_duplicate_when_factory_overrides_scanned_scene(
    pack_tree,
) -> None:
    registry = _scan_scene(pack_tree)
    registry.register("forest", lambda: Scene(effect_packs=[], rule_packs=[]))

    assert registry.names().count("forest") == 1
