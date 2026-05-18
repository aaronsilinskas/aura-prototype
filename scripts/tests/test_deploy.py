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

    (root / "engine").mkdir()
    (root / "engine" / "timer.py").write_text("# timer")

    (root / "magic").mkdir()
    (root / "magic" / "aura.py").write_text("# aura")

    (root / "rules").mkdir()
    (root / "rules" / "__init__.py").write_text("")


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
