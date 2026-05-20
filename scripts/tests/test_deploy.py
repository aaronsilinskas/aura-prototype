import os
from pathlib import Path

from scripts.deploy import deploy

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
        deploy(None, mount, source_root=source)
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

    result = deploy(example, mount, source_root=source)

    assert result == 0
    assert (mount / "code.py").read_text() == "# demo"


def test_no_example_file_leaves_code_py_untouched(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    existing = mount / "code.py"
    existing.write_text("# original")

    deploy(None, mount, source_root=source)

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

    result = deploy(None, mount, source_root=source)

    assert result == 0
    assert (mount / "effects" / "render.py").exists()
    assert (mount / "engine" / "timer.py").exists()
    assert (mount / "magic" / "aura.py").exists()
    assert (mount / "rules" / "__init__.py").exists()


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------


def test_pycache_directories_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

    assert not (mount / "effects" / "__pycache__").exists()


def test_pyc_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    # Add a .pyc at module root level too
    (source / "effects" / "stale.pyc").write_text("")
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

    assert not list((mount / "effects").rglob("*.pyc"))


def test_mpy_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

    assert not list((mount / "effects").rglob("*.mpy"))


def test_tests_directory_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

    assert not (mount / "effects" / "tests" / "__init__.py").exists()


def test_nested_tests_directory_files_are_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

    assert not (mount / "engine" / "tests" / "effects" / "helpers.py").exists()


def test_conftest_py_is_not_copied_to_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source)

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
    dest = mount / "effects" / "render.py"
    dest.write_text("# device copy")

    deploy(None, mount, source_root=source)

    assert dest.read_text() == "# device copy"


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
    src = source / "effects" / "render.py"
    dest = mount / "effects" / "render.py"
    dest.write_text("# device copy")
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 1, _BASE_TIME - 1))  # 1 s behind — within tolerance

    deploy(None, mount, source_root=source)

    assert dest.read_text() == "# device copy"


def test_file_at_fat32_boundary_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    src = source / "effects" / "render.py"
    dest = mount / "effects" / "render.py"
    dest.write_text("# device copy")
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 2, _BASE_TIME - 2))  # exactly 2 s — still within tolerance

    deploy(None, mount, source_root=source)

    assert dest.read_text() == "# device copy"


def test_stale_destination_file_is_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    src = source / "effects" / "render.py"
    dest = mount / "effects" / "render.py"
    dest.write_text("# stale device copy")
    os.utime(src, (_BASE_TIME, _BASE_TIME))
    os.utime(dest, (_BASE_TIME - 3, _BASE_TIME - 3))  # 3 s behind — outside tolerance

    deploy(None, mount, source_root=source)

    assert dest.read_text() == "# render"


# ---------------------------------------------------------------------------
# Dry run (#42)
# ---------------------------------------------------------------------------


def test_dry_run_skips_mount_existence_check(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)

    result = deploy(None, tmp_path / "nonexistent", source_root=source, dry_run=True)

    assert result == 0


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, dry_run=True)

    assert list(mount.rglob("*")) == []


def test_dry_run_output_shows_dry_run_prefix_for_copies(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()

    deploy(None, mount, source_root=source, dry_run=True)

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

    deploy(None, mount, source_root=source)

    assert not stale.exists()


def test_live_py_file_is_not_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    existing = mount / "effects" / "render.py"
    existing.write_text("# device copy")

    deploy(None, mount, source_root=source)

    assert existing.exists()


def test_stale_non_py_file_on_mount_is_not_pruned(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    stale_mpy = mount / "effects" / "old_module.mpy"
    stale_mpy.write_text("")

    deploy(None, mount, source_root=source)

    assert stale_mpy.exists()


def test_code_py_is_never_deleted_from_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    code_py = mount / "code.py"
    code_py.write_text("# running example")

    deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source)

    # effects/ still has live files (render.py was synced), so it must remain
    assert (mount / "effects").exists()


def test_first_time_deploy_with_no_module_dirs_on_mount(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    # mount has no module dirs at all

    result = deploy(None, mount, source_root=source)

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

    deploy(None, mount, source_root=source, dry_run=True)

    assert stale.exists()


def test_dry_run_prune_output_shows_dry_run_prefix(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "effects").mkdir()
    (mount / "effects" / "old_module.py").write_text("# stale")

    deploy(None, mount, source_root=source, dry_run=True)

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

    deploy(None, mount, source_root=source)

    captured = capsys.readouterr()
    assert "2 pruned" in captured.out
