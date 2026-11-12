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

from scripts.ship_list import BOOT_DEVICE, ShipEntry, ship_list

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


def _prune_staging(staging_root: Path, produced: set[Path]) -> int:
    """Delete staged files outside *produced* (with their hash sidecars) and empty dirs."""
    keep = produced | {_hash_path(path) for path in produced if path.suffix == ".mpy"}
    pruned = 0
    for staged_file in sorted(staging_root.rglob("*")):
        if staged_file.is_file() and staged_file not in keep:
            staged_file.unlink()
            if staged_file.suffix != _HASH_SUFFIX:
                pruned += 1
    for directory in sorted(staging_root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return pruned


def build(
    source_root: Path,
    staging_root: Path,
    compile: Callable[[Path, Path], None],
) -> BuildResult:
    """Stage the Ship list in *staging_root*: compiled entries as .mpy, raw entries copied.

    The board's ``boot.py`` is not staged; deploy ships it from source beside ``code.py``.
    """
    # Only boot.py lands on the mount root, so its entry is the one to leave out.
    entries = [entry for entry in ship_list(source_root) if entry.device != BOOT_DEVICE]
    staging_root.mkdir(parents=True, exist_ok=True)
    pruned = _prune_staging(staging_root, {staging_root / entry.device for entry in entries})

    compiled = 0
    skipped = 0
    try:
        for entry in entries:
            if not entry.compiled:
                _copy_raw(source_root, staging_root, entry)
            elif _compile_entry(source_root, staging_root, entry, compile):
                compiled += 1
            else:
                skipped += 1
    except BuildError:
        # Remove the partial staging tree so deploy cannot accidentally sync it.
        shutil.rmtree(staging_root, ignore_errors=True)
        raise

    return BuildResult(compiled=compiled, skipped=skipped, pruned=pruned)


def _copy_raw(source_root: Path, staging_root: Path, entry: ShipEntry) -> None:
    dest = staging_root / entry.device
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / entry.source, dest)


def _compile_entry(
    source_root: Path,
    staging_root: Path,
    entry: ShipEntry,
    compile: Callable[[Path, Path], None],
) -> bool:
    """Compile *entry* into staging; return False when its staged .mpy is already current."""
    src = source_root / entry.source
    dest = staging_root / entry.device
    if _should_skip_compile(src, dest):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    compile(src, dest)
    src_mtime = src.stat().st_mtime
    os.utime(dest, (src_mtime, src_mtime))
    _record_src_hash(src, dest)
    return True
