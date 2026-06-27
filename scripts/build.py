"""Compile device .py modules to .mpy in a gitignored staging tree before deploy."""

import hashlib
import os
import re
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
_HASH_SUFFIX: Final = ".srcsha256"

_REPO_ROOT: Final = Path(__file__).parent.parent
_DEFAULT_MPY_CROSS: Final = str(_REPO_ROOT / "tools" / "mpy-cross")
# Override with MPY_CROSS env var to point at any CircuitPython mpy-cross binary.
# Download the correct version via: scripts/setup_mpy_cross.sh
_MPY_CROSS_BIN: Final = os.environ.get("MPY_CROSS", _DEFAULT_MPY_CROSS)

# Repo-pinned CircuitPython major version.  Must match the major version used by
# the installed mpy-cross binary (see scripts/setup_mpy_cross.sh) and the firmware
# flashed on target devices.  Bump when upgrading CircuitPython.
EXPECTED_CIRCUITPYTHON_MAJOR: Final = 10

_BOOT_OUT_VERSION_RE: Final = re.compile(r"Adafruit CircuitPython (\d+)\.")
_MPY_CROSS_VERSION_RE: Final = re.compile(r"CircuitPython (\d+)\.")


class BuildError(Exception):
    """mpy-cross compile failure; carries the offending file and toolchain error."""


class VersionError(Exception):
    """mpy-cross / CircuitPython version mismatch; deploy aborted before any compile."""


class BuildResult:
    """Summary counts returned by :func:`build`."""

    __slots__ = ("compiled", "pruned", "skipped")

    def __init__(self, compiled: int, skipped: int = 0, pruned: int = 0) -> None:
        self.compiled = compiled
        self.skipped = skipped
        self.pruned = pruned


def mpy_cross_compile(src: Path, dest: Path) -> None:
    """Compile *src* to *dest* using the CircuitPython mpy-cross binary."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [_MPY_CROSS_BIN, str(src), "-o", str(dest)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise BuildError(f"mpy-cross failed on {src}: {stderr}") from exc


def get_mpy_cross_major(mpy_cross_bin: str) -> int:
    """Return the major version integer from ``mpy-cross --version`` output."""
    try:
        result = subprocess.run(
            [mpy_cross_bin, "--version"],
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise VersionError(
            f"mpy-cross not found or failed to run ('{mpy_cross_bin}'). "
            "Install it via: scripts/setup_mpy_cross.sh"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise VersionError(
            f"mpy-cross --version failed (exit {result.returncode}): {stderr}. "
            "Install it via: scripts/setup_mpy_cross.sh"
        )

    output = result.stdout.decode(errors="replace").strip()

    match = _MPY_CROSS_VERSION_RE.search(output)
    if not match:
        raise VersionError(
            f"Cannot parse mpy-cross version from output: {output!r}. "
            "Expected format: 'CircuitPython <major>.<minor>.<patch> on ...; "
            "mpy-cross emitting mpy v<n>'"
        )
    return int(match.group(1))


def parse_circuitpython_major_from_boot_out(boot_out_text: str) -> int:
    """Return the CircuitPython major version integer from *boot_out_text*."""
    match = _BOOT_OUT_VERSION_RE.search(boot_out_text)
    if not match:
        raise VersionError(
            "Cannot parse CircuitPython version from boot_out.txt. "
            f"Content: {boot_out_text[:120]!r}"
        )
    return int(match.group(1))


def validate_mpy_cross_version(mount: Path | None, mpy_cross_bin: str) -> None:
    """Raise :class:`VersionError` when the mpy-cross major version does not match.

    Validates against the device's ``boot_out.txt`` when *mount* is given,
    or against :data:`EXPECTED_CIRCUITPYTHON_MAJOR` for dry-run / CI (``mount=None``).
    """
    if mount is not None:
        boot_out_path = mount / "boot_out.txt"
        if not boot_out_path.exists():
            raise VersionError(
                f"boot_out.txt not found at '{boot_out_path}'. "
                "Ensure the device is mounted and has booted at least once."
            )
        device_major = parse_circuitpython_major_from_boot_out(boot_out_path.read_text())
        expected_major = device_major
        context = f"device CircuitPython {device_major}.x (from boot_out.txt)"
    else:
        expected_major = EXPECTED_CIRCUITPYTHON_MAJOR
        context = f"repo-pinned CircuitPython {EXPECTED_CIRCUITPYTHON_MAJOR}.x"

    actual_major = get_mpy_cross_major(mpy_cross_bin)
    if actual_major != expected_major:
        raise VersionError(
            f"mpy-cross major version {actual_major} does not match {context}. "
            "Install the correct mpy-cross via: scripts/setup_mpy_cross.sh"
        )


def _is_excluded(rel: Path) -> bool:
    for part in rel.parts:
        if part in _EXCLUDE_DIRS:
            return True
    return rel.name in _EXCLUDE_NAMES


def _hash_path(dest_mpy: Path) -> Path:
    return dest_mpy.with_suffix(_HASH_SUFFIX)


def _src_content_hash(src: Path) -> str:
    return hashlib.sha256(src.read_bytes()).hexdigest()


def _should_skip_compile(src: Path, dest_mpy: Path) -> bool:
    """Return True when the staged .mpy is up to date with the source .py.

    Content-hash sidecar makes the skip immune to edits that land within the
    FAT32 2-second mtime tolerance window.
    """
    hp = _hash_path(dest_mpy)
    if not dest_mpy.exists() or not hp.exists():
        return False
    return hp.read_text().strip() == _src_content_hash(src)


def _record_src_hash(src: Path, dest_mpy: Path) -> None:
    _hash_path(dest_mpy).write_text(_src_content_hash(src))


def _prune_staging(source_root: Path, staging_root: Path) -> int:
    """Prune staged .mpy files whose source .py no longer exists."""
    pruned = 0
    for module in MODULE_DIRS:
        src_dir = source_root / module
        dest_dir = staging_root / module
        if not dest_dir.is_dir():
            continue
        for staged_file in sorted(dest_dir.rglob("*.mpy")):
            rel = staged_file.relative_to(dest_dir)
            src_py = src_dir / rel.with_suffix(".py")
            if not src_py.exists():
                staged_file.unlink(missing_ok=True)
                _hash_path(staged_file).unlink(missing_ok=True)
                pruned += 1
    return pruned


def build(
    source_root: Path,
    staging_root: Path,
    compile: Callable[[Path, Path], None],
) -> BuildResult:
    """Populate *staging_root* with compiled .mpy and raw data files ready to sync."""
    staging_root.mkdir(parents=True, exist_ok=True)
    pruned = _prune_staging(source_root, staging_root)

    compiled = 0
    skipped = 0

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
                    if _should_skip_compile(src_file, dest_file):
                        skipped += 1
                        continue
                    compile(src_file, dest_file)
                    src_mtime = src_file.stat().st_mtime
                    os.utime(dest_file, (src_mtime, src_mtime))
                    _record_src_hash(src_file, dest_file)
                    compiled += 1

                elif src_file.suffix in _RAW_SUFFIXES:
                    dest_file = dest_dir / rel
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)

    except BuildError:
        # Remove the partial staging tree so deploy cannot accidentally sync it.
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    return BuildResult(compiled=compiled, skipped=skipped, pruned=pruned)


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
            if _should_skip_compile(src_init, dest_init):
                continue
            dest_init.parent.mkdir(parents=True, exist_ok=True)
            compile(src_init, dest_init)
            src_mtime = src_init.stat().st_mtime
            os.utime(dest_init, (src_mtime, src_mtime))
            _record_src_hash(src_init, dest_init)
