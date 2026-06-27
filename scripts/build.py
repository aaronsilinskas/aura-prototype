"""Compile device .py modules to .mpy in a gitignored staging tree before deploy."""

import os
import shutil
import subprocess
from pathlib import Path

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass

from scripts.deploy import _EXCLUDE_DIRS, _EXCLUDE_NAMES, MODULE_DIRS

_RAW_SUFFIXES: Final = {".json", ".txt", ".wav"}


class BuildError(Exception):
    """mpy-cross compile failure; carries the offending file and toolchain error."""


class BuildResult:
    """Summary counts returned by :func:`build`."""

    __slots__ = ("compiled",)

    def __init__(self, compiled: int) -> None:
        self.compiled = compiled


def mpy_cross_compile(src: Path, dest: Path) -> None:
    """Compile *src* to *dest* via ``python -m mpy_cross``."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["python", "-m", "mpy_cross", str(src), "-o", str(dest)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise BuildError(f"mpy-cross failed on {src}: {stderr}") from exc


def _is_excluded(rel: Path) -> bool:
    for part in rel.parts:
        if part in _EXCLUDE_DIRS:
            return True
    return rel.name in _EXCLUDE_NAMES


def build(
    source_root: Path,
    staging_root: Path,
    compile: Callable[[Path, Path], None],
) -> BuildResult:
    """Populate *staging_root* with compiled .mpy and raw data files ready to sync."""
    # Always start from a clean staging tree.
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir(parents=True)

    compiled = 0

    try:
        for module in MODULE_DIRS:
            src_dir = source_root / module
            if not src_dir.is_dir():
                continue

            _build_intermediate_inits(module, source_root, staging_root, compile)

            dest_dir = staging_root / module

            for src_file in sorted(src_dir.rglob("*")):
                if src_file.is_dir():
                    continue
                rel = src_file.relative_to(src_dir)
                if _is_excluded(rel):
                    continue

                if src_file.suffix == ".py":
                    dest_file = dest_dir / rel.with_suffix(".mpy")
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        compile(src_file, dest_file)
                    except subprocess.CalledProcessError as exc:
                        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
                        raise BuildError(f"mpy-cross failed on {src_file}: {stderr}") from exc
                    # Preserve source mtime so the sync stage can skip unchanged
                    # files on subsequent deploys (FAT32 2-second tolerance).
                    src_mtime = src_file.stat().st_mtime
                    os.utime(dest_file, (src_mtime, src_mtime))
                    compiled += 1

                elif src_file.suffix in _RAW_SUFFIXES:
                    dest_file = dest_dir / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)

    except BuildError:
        # Remove the partial staging tree so deploy cannot accidentally sync it.
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    return BuildResult(compiled=compiled)


def _build_intermediate_inits(
    module: str,
    source_root: Path,
    staging_root: Path,
    compile: Callable[[Path, Path], None],
) -> None:
    parts = Path(module).parts
    for i in range(len(parts) - 1):
        pkg_path = Path(*parts[: i + 1])
        src_init = source_root / pkg_path / "__init__.py"
        if src_init.exists():
            dest_init = staging_root / pkg_path / "__init__.mpy"
            if not dest_init.exists():
                dest_init.parent.mkdir(parents=True, exist_ok=True)
                try:
                    compile(src_init, dest_init)
                except subprocess.CalledProcessError as exc:
                    stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
                    raise BuildError(f"mpy-cross failed on {src_init}: {stderr}") from exc
                src_mtime = src_init.stat().st_mtime
                os.utime(dest_init, (src_mtime, src_mtime))
