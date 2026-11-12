"""Tests for engine.scene.SceneRegistry lookups and the Scene.version / ir_codec fields.

Scanned registries come from ``scan_pack_roots`` over trees laid out by the
shared ``pack_tree`` builder; scan failures are covered by the catalog tests.
In-memory registries are built from ``Scene`` records with the shared
``make_scene`` and ``make_scene_registry`` helpers.
"""

from __future__ import annotations

import pytest

from engine.pack_catalog import scan_pack_roots
from engine.scene import Scene, SceneRegistry
from engine.tests.helpers import make_scene, make_scene_registry
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


def test_a_registry_built_from_no_scenes_has_no_names() -> None:
    registry = make_scene_registry()

    assert registry.names() == []


# ---------------------------------------------------------------------------
# SceneRegistry.get — correct data returned
# ---------------------------------------------------------------------------


def test_get_returns_scene_with_version_parsed_from_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree, version="2.3")

    scene = registry.get("forest")

    assert scene.version is not None
    assert scene.version.major == 2
    assert scene.version.minor == 3


def test_get_returns_scene_with_effect_packs_from_json(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.effect_pack(root, "fx")
    pack_tree.scene(root, "forest", effect_packs=[{"name": "fx", "version": "1.0"}])
    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")

    assert [(pack.name, str(pack.version)) for pack in scene.effect_packs] == [("fx", "1.0")]


def test_get_returns_scene_with_rule_packs_from_json(pack_tree) -> None:
    root = pack_tree.root("ts_flash")
    pack_tree.rule_pack(root, "rules")
    pack_tree.scene(root, "forest", rule_packs=[{"name": "rules", "version": "1.0"}])
    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")

    assert [(pack.name, str(pack.version)) for pack in scene.rule_packs] == [("rules", "1.0")]


def test_get_returns_scene_with_default_ir_codec_when_not_in_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    scene = registry.get("forest")

    assert scene.ir_codec == "aura"


def test_get_returns_scene_with_ir_codec_parsed_from_json(pack_tree) -> None:
    registry = _scan_scene(pack_tree, ir_codec="tag")

    scene = registry.get("forest")

    assert scene.ir_codec == "tag"


# ---------------------------------------------------------------------------
# SceneRegistry.get — the stored record
# ---------------------------------------------------------------------------


def test_get_returns_the_same_record_on_each_call(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    assert registry.get("forest") is registry.get("forest")


def test_get_returns_the_record_the_registry_was_built_from() -> None:
    forest = make_scene()
    registry = make_scene_registry(("forest", forest))

    assert registry.get("forest") is forest


# ---------------------------------------------------------------------------
# SceneRegistry.get — unknown name
# ---------------------------------------------------------------------------


def test_get_raises_value_error_for_unknown_scene_name() -> None:
    registry = make_scene_registry()

    with pytest.raises(ValueError, match="Unknown scene"):
        registry.get("nonexistent")


# ---------------------------------------------------------------------------
# SceneRegistry.resolve_known — known-scene check
# ---------------------------------------------------------------------------


def test_resolve_known_returns_a_scanned_scene_name(pack_tree) -> None:
    registry = _scan_scene(pack_tree)

    assert registry.resolve_known("forest") == "forest"


def test_resolve_known_returns_a_scene_name_the_registry_was_built_with() -> None:
    registry = make_scene_registry(("in_memory", make_scene()))

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
    registry = make_scene_registry()

    with pytest.raises(ValueError, match="Unknown scene"):
        registry.ir_codec_for("nonexistent")


def test_ir_codec_for_answers_the_codec_of_the_record_the_registry_was_built_with() -> None:
    registry = make_scene_registry(("arena", make_scene(ir_codec="tag")))

    assert registry.ir_codec_for("arena") == "tag"


# ---------------------------------------------------------------------------
# SceneRegistry.names — sorted order
# ---------------------------------------------------------------------------


def test_names_returns_scene_names_sorted_alphabetically(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"zebra": {}, "alpha": {}, "mango": {}}).scene_registry

    assert registry.names() == ["alpha", "mango", "zebra"]


def test_names_lists_the_scenes_the_registry_was_built_with() -> None:
    registry = make_scene_registry(("zebra", make_scene()), ("alpha", make_scene()))

    assert registry.names() == ["alpha", "zebra"]
