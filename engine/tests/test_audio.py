from engine.audio import AudioRegistry, scan_sound_dir


def test_register_and_retrieve_a_clip():
    registry = AudioRegistry()

    registry.register("fire_ambient", "/sounds/fire.wav")

    assert registry.path("fire_ambient") == "/sounds/fire.wav"


def test_returns_none_for_unregistered_name():
    registry = AudioRegistry()

    assert registry.path("missing") is None


def test_registering_same_name_twice_overwrites_previous_entry():
    registry = AudioRegistry()
    registry.register("hit", "/sounds/hit_v1.wav")

    registry.register("hit", "/sounds/hit_v2.wav")

    assert registry.path("hit") == "/sounds/hit_v2.wav"


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
