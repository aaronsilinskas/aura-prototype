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
    registry.set_allowed_packs(frozenset({"basic"}))

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
    registry.set_allowed_packs(frozenset({"pack_a", "pack_b"}))

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
    registry.set_allowed_packs(frozenset({"basic"}))

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
    registry.set_allowed_packs(frozenset({"basic"}))

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


# ---------------------------------------------------------------------------
# Pack membership — pack.clip only resolves for packs the active scene
# declared, mirroring EffectResolver's pack.effect membership rule (#814)
# ---------------------------------------------------------------------------


def test_path_raises_when_no_allowed_packs_installed(tmp_path) -> None:
    """A fresh registry's allowed-pack set defaults to None — fail closed."""
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))

    with pytest.raises(ValueError, match="no scene is active"):
        registry.path("basic.win")


def test_path_no_active_scene_error_includes_the_clip_name() -> None:
    registry = AudioRegistry()

    with pytest.raises(ValueError, match=re.escape("basic.win")):
        registry.path("basic.win")


def test_path_raises_for_pack_not_declared_by_active_scene(tmp_path) -> None:
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))
    registry.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="basic"):
        registry.path("basic.win")


def test_undeclared_pack_error_does_not_say_unknown_sound(tmp_path) -> None:
    """The pack exists in the base — it just isn't declared by the active
    scene — so the message must be honest and distinct from 'Unknown sound'.
    """
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))
    registry.set_allowed_packs(frozenset({"other"}))

    try:
        registry.path("basic.win")
    except ValueError as exc:
        assert "Unknown" not in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_path_membership_checked_before_base_lookup() -> None:
    """A clip absent from the base entirely still fails with the not-declared
    message (not 'Unknown sound') when its pack also isn't in the allowed
    set — membership is checked first.
    """
    registry = AudioRegistry()
    registry.set_allowed_packs(frozenset({"other"}))

    with pytest.raises(ValueError, match="not declared"):
        registry.path("basic.win")


def test_path_succeeds_for_declared_pack(tmp_path) -> None:
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))
    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.win") == str(tmp_path / "win.wav")


def test_set_allowed_packs_none_clears_pack_prefix_resolution(tmp_path) -> None:
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))
    registry.set_allowed_packs(frozenset({"basic"}))

    registry.set_allowed_packs(None)

    with pytest.raises(ValueError, match="no scene is active"):
        registry.path("basic.win")


def test_set_allowed_packs_replaces_previous_set(tmp_path) -> None:
    (tmp_path / "win.wav").write_bytes(b"")
    registry = AudioRegistry()
    registry.scan_pack_sounds("basic", str(tmp_path))
    registry.set_allowed_packs(frozenset({"other"}))

    registry.set_allowed_packs(frozenset({"basic"}))

    assert registry.path("basic.win") == str(tmp_path / "win.wav")


def test_scene_prefix_resolution_unaffected_by_missing_allowed_packs() -> None:
    """scene.-prefixed names are scene-local and never gated by allowed packs."""
    registry = AudioRegistry()
    registry.set_scene_sounds({"win": "/sounds/win.wav"})
    # No set_allowed_packs call at all — pack.* would fail closed, but scene.* must not.

    assert registry.path("scene.win") == "/sounds/win.wav"
