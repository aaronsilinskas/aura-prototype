"""Tests for scene-local sound discovery: ``scan_pack_roots`` scanning each
scene's sounds/ subdirectory into a per-scene, bare-keyed sound map carried on
the Scene, mirroring local_effect_registry / local_rule_registry discovery.
"""

from __future__ import annotations

from engine.pack_catalog import scan_pack_roots
from engine.scene import Scene

ROOT_NAME = "tss_flash"


# ---------------------------------------------------------------------------
# sounds/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_sounds_folder_wavs_are_in_its_local_sound_map(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", sounds=["victory_sting"])

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    assert "victory_sting" in scene.local_sound_map


def test_a_local_sound_maps_its_bare_stem_to_its_wav_path(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    scene_dir = pack_tree.scene(root, "forest", sounds=["victory_sting"])

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("forest")
    expected_path = str(scene_dir / "sounds" / "victory_sting.wav")
    assert scene.local_sound_map["victory_sting"] == expected_path


def test_a_scene_without_a_sounds_folder_has_an_empty_local_sound_map(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "bare_scene")

    registry = scan_pack_roots([str(root)]).scene_registry

    scene = registry.get("bare_scene")
    assert scene.local_sound_map == {}


def test_each_fresh_scene_gets_the_same_local_sound_map(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", sounds=["chime"])

    registry = scan_pack_roots([str(root)]).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_sound_map == scene_b.local_sound_map


def test_mutating_a_local_sound_map_does_not_affect_the_next_get(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", sounds=["chime"])

    registry = scan_pack_roots([str(root)]).scene_registry

    scene_a = registry.get("forest")
    scene_a.local_sound_map["chime"] = "/tampered/path.wav"
    scene_b = registry.get("forest")

    assert scene_b.local_sound_map["chime"] != "/tampered/path.wav"


def test_a_scenes_local_sounds_are_not_visible_to_another_scene(pack_tree) -> None:
    root = pack_tree.root(ROOT_NAME)
    pack_tree.scene(root, "forest", sounds=["secret_chime"])
    pack_tree.scene(root, "cave")

    registry = scan_pack_roots([str(root)]).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_chime" not in cave_scene.local_sound_map


def test_scene_constructed_directly_has_empty_local_sound_map() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])
    assert scene.local_sound_map == {}
