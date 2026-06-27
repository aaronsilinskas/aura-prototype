import json
import os
from pathlib import Path

from hardware.shared.device_config import DEFAULT_DEVICE_CONFIG, parse_device_config
from scripts.deploy import deploy


def fake_compile(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"FAKE_MPY:{src.name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_source_tree(root: Path) -> None:
    """Create a minimal fake source tree that mirrors the real repo layout."""
    (root / "effects").mkdir()
    (root / "effects" / "render.py").write_text("# render")
    (root / "effects" / "__pycache__").mkdir()
    (root / "effects" / "__pycache__" / "render.cpython-312.pyc").write_text("")
    (root / "effects" / "render.mpy").write_text("")
    (root / "effects" / "tests").mkdir()
    (root / "effects" / "tests" / "__init__.py").write_text("")

    (root / "engine").mkdir()
    (root / "engine" / "timer.py").write_text("# timer")
    (root / "engine" / "tests" / "effects").mkdir(parents=True)
    (root / "engine" / "tests" / "effects" / "helpers.py").write_text("")

    (root / "magic").mkdir()
    (root / "magic" / "aura.py").write_text("# aura")

    (root / "rules").mkdir()
    (root / "rules" / "__init__.py").write_text("")
    (root / "rules" / "conftest.py").write_text("")

    (root / "hardware").mkdir()
    (root / "hardware" / "__init__.py").write_text("")
    (root / "hardware" / "shared").mkdir()
    (root / "hardware" / "shared" / "__init__.py").write_text("")
    (root / "hardware" / "shared" / "matrix_output.py").write_text("# matrix_output")


# ---------------------------------------------------------------------------
# Mount validation
# ---------------------------------------------------------------------------


def test_nonexistent_mount_exits_with_nonzero_code(tmp_path: Path) -> None:
    result = deploy(None, tmp_path / "nonexistent")
    assert result != 0


def test_file_instead_of_directory_as_mount_exits_with_nonzero_code(tmp_path: Path) -> None:
    mount_file = tmp_path / "not_a_dir"
    mount_file.write_text("oops")
    result = deploy(None, mount_file)
    assert result != 0


def test_read_only_mount_exits_with_nonzero_code(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        result = deploy(None, mount)
        assert result != 0
    finally:
        mount.chmod(0o755)


def test_read_only_mount_prints_error_message(tmp_path: Path, capsys) -> None:
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        deploy(None, mount)
        captured = capsys.readouterr()
        assert "read-only" in captured.err
        assert "Ctrl+C" in captured.err
    finally:
        mount.chmod(0o755)


def test_read_only_mount_copies_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    mount.chmod(0o555)
    try:
        deploy(None, mount, source_root=source, compile=fake_compile)
        assert not list(mount.rglob("*"))
    finally:
        mount.chmod(0o755)


# ---------------------------------------------------------------------------
# Example file deploy
# ---------------------------------------------------------------------------


def test_example_file_is_deployed_as_code_py(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "my_demo.py"
    example.write_text("# demo")

    result = deploy(example, mount, source_root=source, compile=fake_compile)

    assert result == 0
    assert (mount / "code.py").read_text() == "# demo"


def test_example_file_is_always_deployed_even_when_up_to_date(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    example = source / "new_demo.py"
    example.write_text("# new demo")
    # Simulate an older example already deployed as code.py with the same mtime
    existing = mount / "code.py"
    existing.write_text("# old demo")
    import os

    os.utime(existing, (example.stat().st_mtime, example.stat().st_mtime))

    deploy(example, mount, source_root=source, compile=fake_compile)

    assert existing.read_text() == "# new demo"


def test_no_example_file_leaves_code_py_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing = mount / "code.py"
    existing.write_text("# original")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert existing.read_text() == "# original"


# ---------------------------------------------------------------------------
# Module directory sync
# ---------------------------------------------------------------------------


def test_module_directories_are_synced_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    result = deploy(None, mount, source_root=source, compile=fake_compile)

    assert result == 0
    assert (mount / "effects" / "render.mpy").exists()
    assert (mount / "engine" / "timer.mpy").exists()
    assert (mount / "magic" / "aura.mpy").exists()
    assert (mount / "rules" / "__init__.mpy").exists()


def test_hardware_subdirectory_modules_are_deployed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert (mount / "hardware" / "__init__.mpy").exists()
    assert (mount / "hardware" / "shared" / "__init__.mpy").exists()
    assert (mount / "hardware" / "shared" / "matrix_output.mpy").exists()


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------


def test_pycache_directories_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not (mount / "effects" / "__pycache__").exists()


def test_pyc_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    # Add a .pyc at module root level too
    (source / "effects" / "stale.pyc").write_text("")
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not list((mount / "effects").rglob("*.pyc"))


def test_mpy_files_are_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert (mount / "effects" / "render.mpy").exists()


def test_ds_store_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    (source / "effects" / ".DS_Store").write_bytes(b"")
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not (mount / "effects" / ".DS_Store").exists()


def test_tests_directory_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not (mount / "effects" / "tests" / "__init__.py").exists()


def test_nested_tests_directory_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not (mount / "engine" / "tests" / "effects" / "helpers.py").exists()


def test_conftest_py_is_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not (mount / "rules" / "conftest.py").exists()


# ---------------------------------------------------------------------------
# Skip logic (existing destination = up to date for slice 1)
# ---------------------------------------------------------------------------


def test_existing_destination_file_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    # The device now carries .mpy files; a fresh .mpy should not be overwritten.
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert dest.read_bytes() == b"DEVICE_MPY"


# ---------------------------------------------------------------------------
# Skip logic — FAT32 mtime tolerance (#40)
# ---------------------------------------------------------------------------

_BASE_TIME = 1_000_000.0


def test_file_within_fat32_tolerance_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    # The mtime skip is compared against the staging .mpy, not the source .py.
    # Pre-populate the device with a sentinel .mpy that looks fresh.
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")
    # We set a known mtime on the source .py; fake_compile will produce a staging
    # .mpy with approximately that mtime.  Then we set the dest mtime 1 s behind —
    # within the 2-second FAT32 tolerance — so the sync should skip it.
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 1, _BASE_TIME - 1))  # 1 s behind — within tolerance

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert dest.read_bytes() == b"DEVICE_MPY"


def test_file_at_fat32_boundary_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"DEVICE_MPY")
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 2, _BASE_TIME - 2))  # exactly 2 s — still within tolerance

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert dest.read_bytes() == b"DEVICE_MPY"


def test_stale_destination_file_is_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    dest = mount / "effects" / "render.mpy"
    dest.write_bytes(b"STALE_MPY")
    src = source / "effects" / "render.py"
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 3, _BASE_TIME - 3))  # 3 s behind — outside tolerance

    deploy(None, mount, source_root=source, compile=fake_compile)

    # fake_compile writes "FAKE_MPY:<name>" — the stale copy must be replaced.
    assert dest.read_text() == "FAKE_MPY:render.py"


# ---------------------------------------------------------------------------
# Dry run (#42)
# ---------------------------------------------------------------------------


def test_dry_run_skips_mount_existence_check(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)

    result = deploy(
        None, tmp_path / "nonexistent", source_root=source, compile=fake_compile, dry_run=True
    )

    assert result == 0


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile, dry_run=True)

    assert list(mount.rglob("*")) == []


def test_dry_run_output_shows_dry_run_prefix_for_copies(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile, dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY RUN] COPY" in captured.out


# ---------------------------------------------------------------------------
# Pruning stale files (#72)
# ---------------------------------------------------------------------------


def test_stale_py_file_is_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "old_module.py"
    stale.write_text("# stale")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not stale.exists()


def test_live_mpy_file_is_not_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    # The device carries .mpy files; a live .mpy that corresponds to a source .py
    # should remain on the device (it is a valid compiled artefact).
    existing = mount / "effects" / "render.mpy"
    existing.write_bytes(b"DEVICE_MPY")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert existing.exists()


def test_stale_excluded_suffix_file_on_mount_is_not_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale_pyc = mount / "effects" / "old_module.pyc"
    stale_pyc.write_text("")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert stale_pyc.exists()


def test_stale_wav_file_is_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    (source / "effects" / "sounds").mkdir()
    (source / "effects" / "sounds" / "active.wav").write_bytes(b"")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "sounds").mkdir(parents=True)
    stale_wav = mount / "effects" / "sounds" / "old_sound.wav"
    stale_wav.write_bytes(b"")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not stale_wav.exists()


def test_code_py_is_never_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    code_py = mount / "code.py"
    code_py.write_text("# running example")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert code_py.exists()


def test_files_outside_module_dirs_are_not_deleted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    lib = mount / "lib"
    lib.mkdir()
    lib_file = lib / "neopixel.py"
    lib_file.write_text("# neopixel")
    settings = mount / "settings.toml"
    settings.write_text("[wifi]")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert lib_file.exists()
    assert settings.exists()


def test_excluded_path_files_on_mount_are_not_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "tests").mkdir(parents=True)
    legacy_test = mount / "effects" / "tests" / "old_test.py"
    legacy_test.write_text("# legacy test")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert legacy_test.exists()


def test_empty_subdirectory_is_removed_after_pruning(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "steps").mkdir(parents=True)
    stale = mount / "effects" / "steps" / "old_step.py"
    stale.write_text("# stale step")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not stale.exists()
    assert not (mount / "effects" / "steps").exists()


def test_module_root_removed_when_fully_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    # Only create source dirs that don't include 'effects'
    (source / "engine").mkdir()
    (source / "engine" / "timer.py").write_text("# timer")
    (source / "magic").mkdir()
    (source / "magic" / "aura.py").write_text("# aura")
    (source / "rules").mkdir()
    (source / "rules" / "__init__.py").write_text("")
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "render.py"
    stale.write_text("# stale render")

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert not stale.exists()
    assert not (mount / "effects").exists()


def test_non_empty_directory_is_not_removed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects" / "steps").mkdir(parents=True)
    stale = mount / "effects" / "steps" / "old_step.py"
    stale.write_text("# stale")

    deploy(None, mount, source_root=source, compile=fake_compile)

    # effects/ still has live files (render.py was synced), so it must remain
    assert (mount / "effects").exists()


def test_first_time_deploy_with_no_module_dirs_on_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    # mount has no module dirs at all

    result = deploy(None, mount, source_root=source, compile=fake_compile)

    assert result == 0


def test_dry_run_does_not_delete_stale_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale = mount / "effects" / "old_module.py"
    stale.write_text("# stale")

    deploy(None, mount, source_root=source, compile=fake_compile, dry_run=True)

    assert stale.exists()


def test_dry_run_prune_output_shows_dry_run_prefix(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    (mount / "effects" / "old_module.py").write_text("# stale")

    deploy(None, mount, source_root=source, compile=fake_compile, dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY RUN] PRUNE" in captured.out


def test_summary_includes_pruned_count(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    (mount / "effects" / "old_a.py").write_text("# stale")
    (mount / "effects" / "old_b.py").write_text("# stale")

    deploy(None, mount, source_root=source, compile=fake_compile)

    captured = capsys.readouterr()
    assert "2 pruned" in captured.out


# ---------------------------------------------------------------------------
# --scene flag: write scene to aura-device.json (#489)
# ---------------------------------------------------------------------------


def test_scene_flag_sets_scene_key_in_existing_device_config(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing_config = {
        "pixels": [{"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}],
        "buttons": ["D9"],
        "audio": {"voices": 2, "max_volume": 0.5, "clips": {}},
    }
    (mount / "aura-device.json").write_text(json.dumps(existing_config))

    deploy(None, mount, source_root=source, compile=fake_compile, scene="red_light_green_light")

    result = json.loads((mount / "aura-device.json").read_text())
    assert result["scene"] == "red_light_green_light"


def test_scene_flag_preserves_other_keys_in_existing_device_config(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing_config = {
        "pixels": [{"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}],
        "buttons": ["D9"],
        "audio": {"voices": 2, "max_volume": 0.5, "clips": {}},
    }
    (mount / "aura-device.json").write_text(json.dumps(existing_config))

    deploy(None, mount, source_root=source, compile=fake_compile, scene="tag")

    result = json.loads((mount / "aura-device.json").read_text())
    assert result["buttons"] == ["D9"]
    assert result["audio"]["voices"] == 2
    assert result["pixels"] == existing_config["pixels"]


def test_scene_flag_seeds_default_device_config_when_file_is_absent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile, scene="hardware_test")

    result = json.loads((mount / "aura-device.json").read_text())
    assert result["scene"] == "hardware_test"
    for key in DEFAULT_DEVICE_CONFIG:
        assert key in result
    parse_device_config(result)


def test_omitting_scene_flag_leaves_existing_device_config_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    original_content = json.dumps({"pixels": [], "buttons": ["D9"], "scene": "tag"})
    device_config_path = mount / "aura-device.json"
    device_config_path.write_text(original_content)

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert device_config_path.read_text() == original_content


def test_scene_flag_with_dry_run_leaves_device_config_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    original_content = json.dumps({"pixels": [], "buttons": ["D9"], "scene": "tag"})
    device_config_path = mount / "aura-device.json"
    device_config_path.write_text(original_content)

    deploy(
        None, mount, source_root=source, compile=fake_compile, scene="hardware_test", dry_run=True
    )

    assert device_config_path.read_text() == original_content


# ---------------------------------------------------------------------------
# Build integration: deploy compiles .py to .mpy via build stage (#514)
# ---------------------------------------------------------------------------


def test_deploy_ships_mpy_not_py_for_compiled_modules(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert (mount / "effects" / "render.mpy").exists()
    assert not (mount / "effects" / "render.py").exists()


def test_deploy_ships_data_files_raw(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    (source / "packs").mkdir()
    (source / "packs" / "data.json").write_text('{"key": "value"}')
    (source / "packs" / "sounds").mkdir()
    (source / "packs" / "sounds" / "click.wav").write_bytes(b"RIFF")
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    assert (mount / "packs" / "data.json").read_text() == '{"key": "value"}'
    assert (mount / "packs" / "sounds" / "click.wav").read_bytes() == b"RIFF"


def test_deploy_summary_includes_compiled_count(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, compile=fake_compile)

    captured = capsys.readouterr()
    assert "compiled" in captured.out


def test_deploy_compile_failure_returns_nonzero_exit_code(tmp_path: Path) -> None:
    from scripts.build import BuildError

    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    def always_fails(src: Path, dest: Path) -> None:
        raise BuildError(f"mpy-cross failed on {src}: SyntaxError")

    result = deploy(None, mount, source_root=source, compile=always_fails)

    assert result != 0


def test_deploy_compile_failure_leaves_mount_untouched(tmp_path: Path) -> None:
    from scripts.build import BuildError

    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    def always_fails(src: Path, dest: Path) -> None:
        raise BuildError(f"mpy-cross failed on {src}: SyntaxError")

    deploy(None, mount, source_root=source, compile=always_fails)

    assert list(mount.rglob("*")) == []


def test_deploy_compile_failure_prints_error_with_file_and_toolchain_output(
    tmp_path: Path, capsys
) -> None:
    from scripts.build import BuildError

    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    failed: list[str] = []

    def first_fails(src: Path, dest: Path) -> None:
        if not failed:
            failed.append(src.name)
            raise BuildError(f"mpy-cross failed on {src}: SyntaxError: oops")
        fake_compile(src, dest)

    deploy(None, mount, source_root=source, compile=first_fails)

    captured = capsys.readouterr()
    assert failed[0] in captured.err
    assert "SyntaxError" in captured.err
