import re

import pytest

from engine.audio import AudioRegistry, scan_sound_dir

# ---------------------------------------------------------------------------
# scan_sound_dir — public helper
# ---------------------------------------------------------------------------


def test_scan_sound_dir_maps_wav_stem_to_its_path(tmp_path) -> None:
    (tmp_path / "fire_shot_start.wav").write_bytes(b"")

    result = scan_sound_dir(str(tmp_path))

    assert result == {"fire_shot_start": str(tmp_path / "fire_shot_start.wav")}


def test_scan_sound_dir_maps_every_wav_file_in_the_directory(tmp_path) -> None:
    (tmp_path / "fire.wav").write_bytes(b"")
    (tmp_path / "water.wav").write_bytes(b"")

    result = scan_sound_dir(str(tmp_path))

    assert set(result.keys()) == {"fire", "water"}


def test_scan_sound_dir_ignores_non_wav_files(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("")
    (tmp_path / "fire.wav").write_bytes(b"")

    result = scan_sound_dir(str(tmp_path))

    assert result == {"fire": str(tmp_path / "fire.wav")}


def test_scan_sound_dir_ignores_a_directory_named_like_a_wav_file(tmp_path) -> None:
    (tmp_path / "looks_like.wav").mkdir()
    (tmp_path / "real_clip.wav").write_bytes(b"")

    result = scan_sound_dir(str(tmp_path))

    assert result == {"real_clip": str(tmp_path / "real_clip.wav")}


def test_scan_sound_dir_returns_empty_map_for_directory_with_no_wav_files(
    tmp_path,
) -> None:
    (tmp_path / "notes.txt").write_text("")

    result = scan_sound_dir(str(tmp_path))

    assert result == {}


def test_scan_sound_dir_returns_empty_map_for_missing_directory(tmp_path) -> None:
    missing = tmp_path / "does_not_exist"

    result = scan_sound_dir(str(missing))

    assert result == {}


# ---------------------------------------------------------------------------
# AudioRegistry.scan_pack_sounds — base population, pack-qualified
# ---------------------------------------------------------------------------


def test_scan_pack_sounds_resolves_clip_qualified_by_pack_name(tmp_path) -> None:
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()

    registry.scan_pack_sounds("basic", str(tmp_path))

    assert registry.path("basic.win") == str(tmp_path / "win.wav")


def test_scan_pack_sounds_from_two_packs_sharing_a_stem_do_not_collide(tmp_path) -> None:
    pack_a = tmp_path / "pack_a"
    pack_a.mkdir()
    (pack_a / "win.wav").write_bytes(b"")
    pack_b = tmp_path / "pack_b"
    pack_b.mkdir()
    (pack_b / "win.wav").write_bytes(b"")
    registry = AudioRegistry()

    registry.scan_pack_sounds("pack_a", str(pack_a))
    registry.scan_pack_sounds("pack_b", str(pack_b))

    assert registry.path("pack_a.win") == str(pack_a / "win.wav")
    assert registry.path("pack_b.win") == str(pack_b / "win.wav")


# ---------------------------------------------------------------------------
# AudioRegistry.path — prefix routing
# ---------------------------------------------------------------------------


def test_path_with_scene_prefix_resolves_against_the_active_overlay(tmp_path) -> None:
    (tmp_path / "fire_shot_start.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.set_scene_sounds(scan_sound_dir(str(tmp_path)))

    assert registry.path("scene.fire_shot_start") == str(tmp_path / "fire_shot_start.wav")


def test_path_with_pack_prefix_resolves_against_the_base(tmp_path) -> None:
    (tmp_path / "game_over.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))

    assert registry.path("basic.game_over") == str(tmp_path / "game_over.wav")


def test_path_with_scene_prefix_ignores_a_base_entry_of_the_same_stem(tmp_path) -> None:
    """scene. and <pack>. are separate namespaces: a scene can specialise a
    shared clip without the base entry leaking through."""
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


# ---------------------------------------------------------------------------
# AudioRegistry.path — raises rather than returning None
# ---------------------------------------------------------------------------


def test_path_with_unprefixed_name_raises_naming_the_reference() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match="missing"):
        registry.path("missing")


def test_path_with_scene_prefix_and_no_active_overlay_raises() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


def test_path_with_scene_prefix_absent_from_the_active_overlay_raises() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"fire_shot_start": "/sounds/fire_shot_start.wav"})

    with pytest.raises(ValueError, match=re.escape("scene.win")):
        registry.path("scene.win")


def test_path_with_pack_prefix_absent_from_the_base_raises() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match=re.escape("basic.win")):
        registry.path("basic.win")


# ---------------------------------------------------------------------------
# AudioRegistry.set_scene_sounds — overlay swap
# ---------------------------------------------------------------------------


def test_set_scene_sounds_none_clears_the_overlay() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/win.wav"})

    registry.set_scene_sounds(None)

    with pytest.raises(ValueError):
        registry.path("scene.win")


def test_set_scene_sounds_replaces_the_previous_overlay() -> None:
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/a/win.wav"})

    registry.set_scene_sounds({"win": "/sounds/b/win.wav"})

    assert registry.path("scene.win") == "/sounds/b/win.wav"
