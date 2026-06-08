"""Tests for engine.scene.SceneRegistry and Scene.version field."""

from __future__ import annotations

import json

import pytest

from engine.scene import Scene, SceneRegistry
from engine.version import Version

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_scene_json(path, data: dict) -> None:
    """Write *data* as JSON to *path* / scene.json."""
    (path / "scene.json").write_text(json.dumps(data))


def _minimal_scene_json(**overrides) -> dict:
    """Return a minimal valid scene.json dict, with any *overrides* applied."""
    base = {
        "version": "1.0",
        "effect_packs": [],
        "rule_packs": [],
    }
    base.update(overrides)
    return base


def _make_scene_dir(root, name: str, **json_overrides) -> None:
    """Create a named subdirectory under *root* with a valid scene.json."""
    scene_dir = root / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    _write_scene_json(scene_dir, _minimal_scene_json(**json_overrides))


# ---------------------------------------------------------------------------
# Scene.version field
# ---------------------------------------------------------------------------


def test_scene_version_field_is_accessible_after_construction() -> None:
    v = Version(1, 2)
    scene = Scene(effect_packs=[], rule_packs=[], version=v)

    assert scene.version is v


def test_scene_version_defaults_to_none_when_not_provided() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])

    assert scene.version is None


def test_scene_version_stores_major_and_minor_values() -> None:
    v = Version(2, 0)
    scene = Scene(effect_packs=[], rule_packs=[], version=v)

    assert scene.version.major == 2
    assert scene.version.minor == 0


# ---------------------------------------------------------------------------
# SceneRegistry — construction
# ---------------------------------------------------------------------------


def test_scene_registry_names_is_empty_on_construction() -> None:
    registry = SceneRegistry()

    assert registry.names() == []


# ---------------------------------------------------------------------------
# SceneRegistry.scan_dir — discovery
# ---------------------------------------------------------------------------


def test_scan_dir_discovers_subdirectory_with_scene_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest")
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

    assert "forest" in registry.names()


def test_scan_dir_ignores_subdirectory_without_scene_json(tmp_path) -> None:
    (tmp_path / "no_json").mkdir()
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

    assert registry.names() == []


def test_scan_dir_ignores_plain_files_at_top_level(tmp_path) -> None:
    (tmp_path / "readme.txt").write_text("hello")
    _make_scene_dir(tmp_path, "cave")
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

    assert registry.names() == ["cave"]


def test_scan_dir_discovers_multiple_scene_directories(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest")
    _make_scene_dir(tmp_path, "cave")
    _make_scene_dir(tmp_path, "arena")
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

    assert sorted(registry.names()) == ["arena", "cave", "forest"]


def test_scan_dir_on_empty_directory_registers_no_scenes(tmp_path) -> None:
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

    assert registry.names() == []


# ---------------------------------------------------------------------------
# SceneRegistry.scan_dir — idempotency
# ---------------------------------------------------------------------------


def test_scan_dir_called_twice_with_same_path_is_a_no_op(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest")
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))
    registry.scan_dir(str(tmp_path))  # no-op

    assert registry.names() == ["forest"]


def test_scan_dir_second_call_does_not_pick_up_scenes_added_after_first_scan(
    tmp_path,
) -> None:
    _make_scene_dir(tmp_path, "forest")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    # Add a new scene after the first scan.
    _make_scene_dir(tmp_path, "cave")
    registry.scan_dir(str(tmp_path))  # no-op

    assert "cave" not in registry.names()


# ---------------------------------------------------------------------------
# SceneRegistry.scan_dir — name collision
# ---------------------------------------------------------------------------


def test_scan_dir_raises_when_same_scene_name_comes_from_different_directory(
    tmp_path,
) -> None:
    src_a = tmp_path / "src_a"
    src_b = tmp_path / "src_b"
    src_a.mkdir()
    src_b.mkdir()
    _make_scene_dir(src_a, "forest")
    _make_scene_dir(src_b, "forest")

    registry = SceneRegistry()
    registry.scan_dir(str(src_a))

    with pytest.raises(ValueError):
        registry.scan_dir(str(src_b))


# ---------------------------------------------------------------------------
# SceneRegistry.scan_dir — validation errors
# ---------------------------------------------------------------------------


def test_scan_dir_raises_when_version_field_is_missing(tmp_path) -> None:
    scene_dir = tmp_path / "bad"
    scene_dir.mkdir()
    _write_scene_json(scene_dir, {"effect_packs": [], "rule_packs": []})
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="version"):
        registry.scan_dir(str(tmp_path))


def test_scan_dir_raises_when_version_is_malformed(tmp_path) -> None:
    scene_dir = tmp_path / "bad"
    scene_dir.mkdir()
    _write_scene_json(
        scene_dir,
        {"version": "not-a-version", "effect_packs": [], "rule_packs": []},
    )
    registry = SceneRegistry()

    with pytest.raises(ValueError):
        registry.scan_dir(str(tmp_path))


def test_scan_dir_raises_when_effect_packs_field_is_missing(tmp_path) -> None:
    scene_dir = tmp_path / "bad"
    scene_dir.mkdir()
    _write_scene_json(scene_dir, {"version": "1.0", "rule_packs": []})
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="effect_packs"):
        registry.scan_dir(str(tmp_path))


def test_scan_dir_raises_when_rule_packs_field_is_missing(tmp_path) -> None:
    scene_dir = tmp_path / "bad"
    scene_dir.mkdir()
    _write_scene_json(scene_dir, {"version": "1.0", "effect_packs": []})
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="rule_packs"):
        registry.scan_dir(str(tmp_path))


def test_scan_dir_raises_when_unknown_top_level_key_is_present(tmp_path) -> None:
    scene_dir = tmp_path / "bad"
    scene_dir.mkdir()
    _write_scene_json(
        scene_dir,
        {
            "version": "1.0",
            "effect_packs": [],
            "rule_packs": [],
            "unexpected_key": "oops",
        },
    )
    registry = SceneRegistry()

    with pytest.raises(ValueError, match="unexpected_key"):
        registry.scan_dir(str(tmp_path))


# ---------------------------------------------------------------------------
# SceneRegistry.get — correct data returned
# ---------------------------------------------------------------------------


def test_get_returns_scene_with_version_parsed_from_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest", version="2.3")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene = registry.get("forest")

    assert isinstance(scene.version, Version)
    assert scene.version.major == 2
    assert scene.version.minor == 3


def test_get_returns_scene_with_effect_packs_from_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest", effect_packs=[["fx", "1.0"]])
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene = registry.get("forest")

    assert scene.effect_packs == [["fx", "1.0"]]


def test_get_returns_scene_with_rule_packs_from_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest", rule_packs=[["rules", "1.0"]])
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene = registry.get("forest")

    assert scene.rule_packs == [["rules", "1.0"]]


def test_get_returns_scene_with_initial_data_from_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest", initial_data={"score": 0, "level": 5})
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene = registry.get("forest")

    assert scene.initial_data == {"score": 0, "level": 5}


def test_get_returns_scene_with_none_initial_data_when_not_in_json(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene = registry.get("forest")

    assert scene.initial_data is None


# ---------------------------------------------------------------------------
# SceneRegistry.get — fresh instance per call
# ---------------------------------------------------------------------------


def test_get_returns_fresh_scene_on_each_call(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a is not scene_b


def test_get_returns_scenes_with_shared_version_instance(tmp_path) -> None:
    _make_scene_dir(tmp_path, "forest", version="1.0")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")

    assert scene_a.version is scene_b.version


def test_get_returns_fresh_initial_data_so_mutation_does_not_affect_next_call(
    tmp_path,
) -> None:
    _make_scene_dir(tmp_path, "forest", initial_data={"score": 0})
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))

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
# SceneRegistry.names — sorted order
# ---------------------------------------------------------------------------


def test_names_returns_scene_names_sorted_alphabetically(tmp_path) -> None:
    _make_scene_dir(tmp_path, "zebra")
    _make_scene_dir(tmp_path, "alpha")
    _make_scene_dir(tmp_path, "mango")
    registry = SceneRegistry()

    registry.scan_dir(str(tmp_path))

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


def test_register_factory_and_json_scenes_are_indistinguishable_via_public_api(
    tmp_path,
) -> None:
    _make_scene_dir(tmp_path, "from_disk", version="1.0")
    registry = SceneRegistry()
    registry.scan_dir(str(tmp_path))
    registry.register(
        "from_memory",
        lambda: Scene(effect_packs=[], rule_packs=[], version=Version(1, 0)),
    )

    disk_scene = registry.get("from_disk")
    mem_scene = registry.get("from_memory")

    # Both expose the same fields through the same public interface
    assert disk_scene.version.major == 1
    assert disk_scene.version.minor == 0
    assert mem_scene.version.major == 1
    assert mem_scene.version.minor == 0
