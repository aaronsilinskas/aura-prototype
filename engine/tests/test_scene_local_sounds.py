"""Tests for scene-local sound discovery: ``scan_pack_roots`` scanning each
scene's sounds/ subdirectory into a per-scene, bare-keyed sound map carried on
the Scene, mirroring local_effect_registry / local_rule_registry discovery.
"""

from __future__ import annotations

from engine.scene import Scene

# ---------------------------------------------------------------------------
# sounds/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_sounds_folder_wavs_are_in_its_local_sound_map(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": {"sounds": ["victory_sting"]}}).scene_registry

    scene = registry.get("forest")
    assert "victory_sting" in scene.local_sound_map


def test_each_fresh_scene_gets_the_same_local_sound_map(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": {"sounds": ["chime"]}}).scene_registry

    scene_a = registry.get("forest")
    scene_b = registry.get("forest")
    assert scene_a.local_sound_map == scene_b.local_sound_map


def test_mutating_a_local_sound_map_does_not_affect_the_next_get(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": {"sounds": ["chime"]}}).scene_registry

    scene_a = registry.get("forest")
    scene_a.local_sound_map["chime"] = "/tampered/path.wav"
    scene_b = registry.get("forest")

    assert scene_b.local_sound_map["chime"] != "/tampered/path.wav"


def test_a_scenes_local_sounds_are_not_visible_to_another_scene(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"sounds": ["secret_chime"]}, "cave": {}}
    ).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_chime" not in cave_scene.local_sound_map


def test_scene_constructed_directly_has_empty_local_sound_map() -> None:
    scene = Scene(effect_packs=[], rule_packs=[])
    assert scene.local_sound_map == {}
