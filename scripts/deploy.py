"""Deploy a CircuitPython example and module directories to a mounted CIRCUITPY volume.

Usage
-----
    # Deploy an example and sync all modules (compiles .py → .mpy via mpy-cross):
    python scripts/deploy.py examples/hardware/scene_demo.py

    # Sync modules only, without changing code.py:
    python scripts/deploy.py

    # Override the default mount path:
    python scripts/deploy.py examples/hardware/scene_demo.py --mount /Volumes/MYBOARD

mpy-cross
---------
Install with ``uv sync`` (pinned in ``[dependency-groups] dev`` via ``mpy-cross``).
Matches the CircuitPython minor release in use.  Invoked as ``python -m mpy_cross``.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass

# Starter config copied onto a board that has no aura-device.json yet, when
# --scene is used. There is no built-in default; this sample is the seed.
_SAMPLE_DEVICE_CONFIG: Final = Path("examples/aura-device.sample.json")

MODULE_DIRS: Final = [
    "app",
    "effects",
    "engine",
    "hardware/circuitpython",
    "hardware/shared",
    "magic",
    "packs",
    "rules",
]
_EXCLUDE_DIRS: Final = {"__pycache__", "tests"}
_EXCLUDE_NAMES: Final = {"conftest.py"}
_INCLUDE_SUFFIXES: Final = {".py", ".mpy", ".txt", ".json", ".wav"}
_DEFAULT_MOUNT: Final = "/Volumes/CIRCUITPY"


def _is_excluded(rel: Path) -> bool:
    """Return True if a relative path should be excluded from sync."""
    for part in rel.parts:
        if part in _EXCLUDE_DIRS:
            return True
    if rel.name in _EXCLUDE_NAMES:
        return True
    return rel.suffix not in _INCLUDE_SUFFIXES


def _collect_stale_files(src_dir: Path, dest_dir: Path) -> list[Path]:
    """Return files in dest_dir that have no counterpart in src_dir.

    Returns an empty list if dest_dir does not exist.
    Excluded paths (e.g. tests/, __pycache__/) are not considered stale.
    """
    if not dest_dir.is_dir():
        return []
    stale = []
    for dest_file in sorted(dest_dir.rglob("*")):
        if dest_file.is_dir():
            continue
        rel = dest_file.relative_to(dest_dir)
        if _is_excluded(rel):
            continue
        if not (src_dir / rel).exists():
            stale.append(dest_file)
    return stale


def _should_skip(src: Path, dest: Path) -> bool:
    """Return True if the destination file is already up to date.

    A destination is considered fresh when its mtime is within 2 seconds of the
    source mtime. The 2-second tolerance accounts for FAT32's mtime truncation:
    ``shutil.copy2`` preserves the source mtime, but FAT32 rounds it down to the
    nearest even second, so a strict ``>=`` check would always re-copy on the
    next run.
    """
    if not dest.exists():
        return False
    return dest.stat().st_mtime >= src.stat().st_mtime - 2


def _copy_intermediate_inits(
    module: str,
    sync_root: Path,
    mount: Path,
    copied: "list[Path]",
    skipped: "list[Path]",
    dry_run: bool,
    use_source: bool = False,
) -> None:
    parts = Path(module).parts
    for i in range(len(parts) - 1):
        pkg_path = Path(*parts[: i + 1])
        if use_source:
            src_init = sync_root / pkg_path / "__init__.py"
        else:
            src_init = sync_root / pkg_path / "__init__.mpy"
            if not src_init.exists():
                src_init = sync_root / pkg_path / "__init__.py"
        if src_init.exists():
            label = str(pkg_path / src_init.name)
            _sync_file(src_init, mount / pkg_path / src_init.name, label, copied, skipped, dry_run)


def _sync_file(
    src: Path,
    dest: Path,
    label: str,
    copied: "list[Path]",
    skipped: "list[Path]",
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copy src to dest unless it should be skipped."""
    if not force and _should_skip(src, dest):
        skipped.append(dest)
        print(f"SKIP  {label} (up to date)")
    elif dry_run:
        copied.append(dest)
        print(f"[DRY RUN] COPY  {label}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(dest)
        print(f"COPY  {label}")


def _write_scene(mount: Path, scene: str, source_root: Path) -> None:
    """Set the ``"scene"`` key in ``aura-device.json``, seeding from the sample if absent.

    A board with no ``aura-device.json`` is seeded from the sample because there
    is no built-in default config to fall back on.
    """
    device_config_path = mount / "aura-device.json"
    if device_config_path.exists():
        config = json.loads(device_config_path.read_text())
    else:
        config = json.loads((source_root / _SAMPLE_DEVICE_CONFIG).read_text())
    config["scene"] = scene
    device_config_path.write_text(json.dumps(config, indent=2))


def deploy(
    example_file: "Path | None",
    mount: Path,
    source_root: "Path | None" = None,
    dry_run: bool = False,
    scene: "str | None" = None,
    compile: "Callable[[Path, Path], None] | None" = None,
    use_source: bool = False,
) -> int:
    """Deploy to mount. Returns 0 on success, 1 on error.

    Args:
        example_file: Path to the example file to copy as ``code.py``.
            Pass ``None`` to sync modules only without touching ``code.py``.
        mount: Path to the mounted CIRCUITPY volume.
        source_root: Root of the source tree. Defaults to ``Path.cwd()``.
        dry_run: When True, skip mount validation and print what would be copied
            without writing any files.
        scene: Scene name to record in ``aura-device.json``; omit to leave it untouched.
        compile: Callable ``(src, dest) -> None`` used to compile each ``.py`` file
            to ``.mpy`` in a staging tree before syncing.  Defaults to the real
            ``mpy_cross_compile`` (requires ``mpy-cross`` installed).  Pass a fake
            for unit tests.  When ``None`` the real compiler is used.
        use_source: When True, skip compilation entirely and sync raw ``.py`` files
            directly from the source tree.  Requires no ``mpy-cross`` toolchain.
    """
    # Import here to avoid a circular import (build imports from deploy).
    from scripts.build import (
        _MPY_CROSS_BIN,
        BuildError,
        VersionError,
        build,
        mpy_cross_compile,
        validate_mpy_cross_version,
    )

    if source_root is None:
        source_root = Path.cwd()

    if not dry_run:
        if not mount.is_dir():
            print(
                f"Error: mount path '{mount}' does not exist or is not a directory.",
                file=sys.stderr,
            )
            return 1

        if not os.access(mount, os.W_OK):
            print(
                "Error: CIRCUITPY is read-only. Press Ctrl+C on the device to stop code.py first.",
                file=sys.stderr,
            )
            return 1

    compiled_count = 0

    if use_source:
        sync_root = source_root
    else:
        if compile is None:
            compile = mpy_cross_compile

        validation_mount = None if dry_run else mount
        try:
            validate_mpy_cross_version(mount=validation_mount, mpy_cross_bin=_MPY_CROSS_BIN)
        except VersionError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        staging_root = source_root / "build"
        try:
            build_result = build(
                source_root=source_root,
                staging_root=staging_root,
                compile=compile,
            )
        except BuildError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        compiled_count = build_result.compiled
        sync_root = staging_root

    if scene is not None and not dry_run:
        _write_scene(mount, scene, source_root)

    copied: list[Path] = []
    skipped: list[Path] = []
    pruned: list[Path] = []

    if example_file is not None:
        _sync_file(example_file, mount / "code.py", "code.py", copied, skipped, dry_run, force=True)

    for module in MODULE_DIRS:
        src_dir = sync_root / module
        dest_dir = mount / module

        if src_dir.is_dir():
            if "/" in module:
                _copy_intermediate_inits(
                    module, sync_root, mount, copied, skipped, dry_run, use_source=use_source
                )
            for src_file in sorted(src_dir.rglob("*")):
                if src_file.is_dir():
                    continue
                rel = src_file.relative_to(src_dir)
                if _is_excluded(rel):
                    continue
                if use_source and src_file.suffix == ".mpy":
                    continue
                label = f"{module}/{rel}"
                _sync_file(src_file, dest_dir / rel, label, copied, skipped, dry_run)

        stale_files = _collect_stale_files(src_dir, dest_dir)
        if use_source and dest_dir.is_dir():
            stale_set = set(stale_files)
            for dest_file in sorted(dest_dir.rglob("*")):
                is_orphaned_mpy = not dest_file.is_dir() and dest_file.suffix == ".mpy"
                if is_orphaned_mpy and dest_file not in stale_set:
                    stale_files.append(dest_file)
                    stale_set.add(dest_file)
        for stale_file in stale_files:
            label = f"{module}/{stale_file.relative_to(dest_dir)}"
            if dry_run:
                pruned.append(stale_file)
                print(f"[DRY RUN] PRUNE  {label}")
            else:
                stale_file.unlink()
                pruned.append(stale_file)
                print(f"PRUNE  {label}")

        if not dry_run and dest_dir.is_dir():
            for d in sorted(dest_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if d.is_dir():
                    try:
                        d.rmdir()
                    except OSError:
                        pass
            try:
                dest_dir.rmdir()
            except OSError:
                pass

    print(
        f"Done. {compiled_count} compiled, "
        f"{len(copied)} copied, {len(skipped)} skipped, {len(pruned)} pruned."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy a CircuitPython example and modules to a CIRCUITPY volume."
    )
    parser.add_argument(
        "example_file",
        nargs="?",
        type=Path,
        default=None,
        help="Example file to deploy as code.py on the device. Omit to sync modules only.",
    )
    parser.add_argument(
        "--mount",
        type=Path,
        default=Path(_DEFAULT_MOUNT),
        help=f"Path to the mounted CIRCUITPY volume (default: {_DEFAULT_MOUNT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be copied without writing any files. Skips mount validation.",
    )
    parser.add_argument(
        "--scene",
        type=str,
        default=None,
        help=(
            "Scene name to record in aura-device.json on the mounted volume. "
            "Combines deploying code and selecting the game into one step. "
            "Omit to leave any existing aura-device.json untouched."
        ),
    )
    parser.add_argument(
        "--source",
        action="store_true",
        default=False,
        help=(
            "Skip compilation and ship raw .py files directly from the source tree. "
            "Useful for reproducing crashes on-device with full tracebacks. "
            "Requires no mpy-cross toolchain."
        ),
    )
    args = parser.parse_args()
    sys.exit(
        deploy(
            args.example_file,
            args.mount,
            dry_run=args.dry_run,
            scene=args.scene,
            use_source=args.source,
        )
    )


if __name__ == "__main__":
    main()
