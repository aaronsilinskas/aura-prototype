"""Tests for scene-local sound discovery: SceneRegistry.scan_dir scanning each
scene's sounds/ subdirectory into a per-scene, bare-keyed sound map carried on
the Scene, mirroring local_effect_registry / local_rule_registry discovery.
"""

from __future__ import annotations

import json

import pytest

from engine.scene import Scene, SceneRegistry

MODULE_PREFIX = "tss"


@pytest.fixture()
def scene_env(tmp_path):
    """Yield a ``tss/`` subdirectory of tmp_path as the scenes root."""
    scenes_root = tmp_path / MODULE_PREFIX
    scenes_root.mkdir()
    return scenes_root


def _write_scene_json(path, data: dict) -> None:
    (path / "scene.json").write_text(json.dumps(data))


def _minimal_scene_json(**overrides) -> dict:
    base = {"version": "1.0", "effect_packs": [], "rule_packs": []}
    base.update(overrides)
    return base


def _make_scene_dir(root, name: str, **json_overrides):
    scene_dir = root / name
    scene_dir.mkdir(parents=True, exist_ok=True)
    _write_scene_json(scene_dir, _minimal_scene_json(**json_overrides))
    return scene_dir


def _make_sounds_subdir(scene_dir, stems: list[str]) -> None:
    """Create a sounds/ subdir under *scene_dir* with a .wav file per stem."""
    sounds_dir = scene_dir / "sounds"
    sounds_dir.mkdir(exist_ok=True)
    for stem in stems:
        (sounds_dir / (stem + ".wav")).write_bytes(b"")


# ---------------------------------------------------------------------------
# scan_dir — sounds/ subdir discovery
# ---------------------------------------------------------------------------


def test_scan_dir_exposes_sounds_subdir_wav_stems_via_local_sound_map(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_sounds_subdir(scene_dir, ["victory_sting"])

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    assert "victory_sting" in scene.local_sound_map


def test_scan_dir_local_sound_map_maps_stem_to_wav_path(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_sounds_subdir(scene_dir, ["victory_sting"])

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("forest")
    expected_path = str(scene_dir / "sounds" / "victory_sting.wav")
    assert scene.local_sound_map["victory_sting"] == expected_path


def test_scan_dir_scene_with_no_sounds_subdir_has_empty_local_sound_map(scene_env) -> None:
    _make_scene_dir(scene_env, "bare_scene")
    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene = registry.get("bare_scene")
    assert scene.local_sound_map == {}


def test_scan_dir_local_sound_map_shared_across_fresh_scene_instances(scene_env) -> None:
    scene_dir = _make_scene_dir(scene_env, "forest")
    _make_sounds_subdir(scene_dir, ["chime"])

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_sound_map is scene_b.local_sound_map


def test_scan_dir_local_sounds_not_visible_to_other_scene(scene_env) -> None:
    scene_a_dir = _make_scene_dir(scene_env, "forest")
    _make_sounds_subdir(scene_a_dir, ["secret_chime"])
    _make_scene_dir(scene_env, "cave")

    registry = SceneRegistry()
    registry.scan_dir(str(scene_env), MODULE_PREFIX)

    cave_scene = registry.get("cave")
    assert "secret_chime" not in cave_scene.local_sound_map


def test_scene_constructed_directly_has_empty_local_sound_map() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])
    assert scene.local_sound_map == {}
