"""Tests for the build stage: compile .py -> .mpy into a staging tree."""

import subprocess
from pathlib import Path

import pytest

from scripts.build import BuildError, build

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fake_compile(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"FAKE_MPY:{src.name}")


def make_source_tree(root: Path) -> None:
    """Create a minimal fake source tree that mirrors the real repo layout."""
    (root / "effects").mkdir()
    (root / "effects" / "__init__.py").write_text("# effects init")
    (root / "effects" / "render.py").write_text("# render")
    (root / "effects" / "__pycache__").mkdir()
    (root / "effects" / "__pycache__" / "render.cpython-312.pyc").write_text("")
    (root / "effects" / "tests").mkdir()
    (root / "effects" / "tests" / "__init__.py").write_text("")

    (root / "engine").mkdir()
    (root / "engine" / "timer.py").write_text("# timer")
    (root / "engine" / "tests").mkdir()
    (root / "engine" / "tests" / "helpers.py").write_text("")

    (root / "magic").mkdir()
    (root / "magic" / "aura.py").write_text("# aura")

    (root / "packs").mkdir()
    (root / "packs" / "__init__.py").write_text("")
    (root / "packs" / "data.json").write_text('{"key": "value"}')
    (root / "packs" / "readme.txt").write_text("notes")
    (root / "packs" / "sounds").mkdir()
    (root / "packs" / "sounds" / "click.wav").write_bytes(b"RIFF")

    (root / "rules").mkdir()
    (root / "rules" / "__init__.py").write_text("")
    (root / "rules" / "conftest.py").write_text("")

    (root / "hardware").mkdir()
    (root / "hardware" / "__init__.py").write_text("")
    (root / "hardware" / "shared").mkdir()
    (root / "hardware" / "shared" / "__init__.py").write_text("# hw shared init")
    (root / "hardware" / "shared" / "matrix_output.py").write_text("# matrix_output")


# ---------------------------------------------------------------------------
# Staging tree: .py files are compiled to .mpy
# ---------------------------------------------------------------------------


def test_python_module_is_compiled_to_mpy_in_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "effects" / "render.mpy").exists()


def test_init_py_is_compiled_to_mpy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "effects" / "__init__.mpy").exists()


def test_source_py_is_not_present_in_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert not (staging / "effects" / "render.py").exists()
    assert not (staging / "effects" / "__init__.py").exists()


def test_all_module_dirs_are_compiled(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "engine" / "timer.mpy").exists()
    assert (staging / "magic" / "aura.mpy").exists()


def test_hardware_subdirectory_modules_are_compiled(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "hardware" / "shared" / "matrix_output.mpy").exists()
    assert (staging / "hardware" / "shared" / "__init__.mpy").exists()


def test_intermediate_package_inits_are_compiled(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "hardware" / "__init__.mpy").exists()


# ---------------------------------------------------------------------------
# Staging tree: data files are copied raw
# ---------------------------------------------------------------------------


def test_json_file_is_copied_raw(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "packs" / "data.json").read_text() == '{"key": "value"}'


def test_txt_file_is_copied_raw(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "packs" / "readme.txt").read_text() == "notes"


def test_wav_file_is_copied_raw(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert (staging / "packs" / "sounds" / "click.wav").read_bytes() == b"RIFF"


# ---------------------------------------------------------------------------
# Staging tree: excluded paths are not present
# ---------------------------------------------------------------------------


def test_tests_directory_is_not_in_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert not (staging / "effects" / "tests").exists()
    assert not (staging / "engine" / "tests").exists()


def test_pycache_is_not_in_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert not (staging / "effects" / "__pycache__").exists()


def test_conftest_py_is_not_in_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    build(source_root=source, staging_root=staging, compile=fake_compile)

    assert not (staging / "rules" / "conftest.mpy").exists()
    assert not (staging / "rules" / "conftest.py").exists()


# ---------------------------------------------------------------------------
# Compile failure aborts the build
# ---------------------------------------------------------------------------


def test_compile_failure_raises_build_error(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"
    target_file = "render.py"

    def failing_compile(src: Path, dest: Path) -> None:
        if src.name == target_file:
            raise subprocess.CalledProcessError(1, "mpy-cross", stderr=b"SyntaxError: bad syntax")
        fake_compile(src, dest)

    with pytest.raises(BuildError) as exc_info:
        build(source_root=source, staging_root=staging, compile=failing_compile)

    assert "render.py" in str(exc_info.value)
    assert "SyntaxError" in str(exc_info.value)


def test_compile_failure_leaves_no_partial_staging_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"
    compiled: list[str] = []

    def first_fails_compile(src: Path, dest: Path) -> None:
        if not compiled:
            compiled.append(src.name)
            raise subprocess.CalledProcessError(1, "mpy-cross", stderr=b"error")
        fake_compile(src, dest)

    with pytest.raises(BuildError):
        build(source_root=source, staging_root=staging, compile=first_fails_compile)

    assert not staging.exists() or not any(staging.rglob("*.mpy"))


# ---------------------------------------------------------------------------
# Return value: compiled count
# ---------------------------------------------------------------------------


def test_build_returns_compiled_count(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_source_tree(source)
    staging = tmp_path / "build"

    result = build(source_root=source, staging_root=staging, compile=fake_compile)

    assert result.compiled > 0


def test_build_compiled_count_matches_py_files_processed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    # Minimal tree: only effects/render.py
    (source / "effects").mkdir()
    (source / "effects" / "render.py").write_text("# render")
    staging = tmp_path / "build"

    result = build(source_root=source, staging_root=staging, compile=fake_compile)

    assert result.compiled == 1
