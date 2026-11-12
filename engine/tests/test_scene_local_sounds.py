"""Tests for scene-local sound discovery: ``scan_pack_roots`` scanning each
scene's sounds/ subdirectory into a per-scene, bare-keyed sound map carried on
the Scene, mirroring local_effect_registry / local_rule_registry discovery.
"""

from __future__ import annotations

from engine.tests.helpers import make_scene

# ---------------------------------------------------------------------------
# sounds/ folder discovery
# ---------------------------------------------------------------------------


def test_a_scenes_sounds_folder_wavs_are_in_its_local_sound_map(pack_tree) -> None:
    registry = pack_tree.scan(scenes={"forest": {"sounds": ["victory_sting"]}}).scene_registry

    scene = registry.get("forest")
    assert "victory_sting" in scene.local_sound_map


def test_a_scenes_local_sounds_are_not_visible_to_another_scene(pack_tree) -> None:
    registry = pack_tree.scan(
        scenes={"forest": {"sounds": ["secret_chime"]}, "cave": {}}
    ).scene_registry

    cave_scene = registry.get("cave")
    assert "secret_chime" not in cave_scene.local_sound_map


def test_a_scene_built_in_memory_has_an_empty_local_sound_map() -> None:
    scene = make_scene()
    assert scene.local_sound_map == {}
