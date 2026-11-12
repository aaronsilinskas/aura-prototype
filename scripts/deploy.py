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
import secrets
import shutil
import sys
from pathlib import Path

if not __package__:
    # Run as a file (python scripts/deploy.py): put the repo root on the path so
    # the package imports below resolve as they do under python -m.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.shared.scene_selection import with_scene_deploy
from scripts.build import (
    BuildError,
    VersionError,
    build,
    mpy_cross_compile,
    validate_mpy_cross_version,
)
from scripts.ship_list import MODULE_DIRS, governed_mount_files, ship_list

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass

DEFAULT_MOUNT: Final = "/Volumes/CIRCUITPY"


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


def _remove_empty_dirs(dest_dir: Path) -> None:
    """Remove every empty directory under *dest_dir*, then *dest_dir* itself if empty."""
    if not dest_dir.is_dir():
        return
    for d in sorted(dest_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    if not any(dest_dir.iterdir()):
        dest_dir.rmdir()


def _write_scene(mount: Path, scene: str) -> None:
    """Set ``default_scene`` and a fresh Scene deploy token in ``aura-boot.json``.

    Merges with any existing keys. A board with no ``aura-boot.json`` gets
    one created fresh holding only these two keys — unlike ``aura-device.json``,
    there is no sample template to seed from (the boot file is trivially
    authored).
    """
    boot_path = mount / "aura-boot.json"
    boot_values = json.loads(boot_path.read_text()) if boot_path.exists() else {}
    boot_values = with_scene_deploy(boot_values, scene, secrets.token_hex(8))
    boot_path.write_text(json.dumps(boot_values, indent=2))


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

    Syncs the Ship list's entries to *mount*, then prunes each mount file the
    list governs but no longer names, and removes every empty directory under
    each module directory.

    Args:
        example_file: Path to the example file to copy as ``code.py``.
            Pass ``None`` to sync modules only without touching ``code.py``
            (or its paired ``boot.py`` -- see below).
        mount: Path to the mounted CIRCUITPY volume.
        source_root: Root of the source tree. Defaults to ``Path.cwd()``.
        dry_run: When True, skip mount validation and print what would be copied
            without writing any files.
        scene: Scene name to record in ``aura-boot.json``'s ``default_scene`` key,
            beside a fresh ``scene_deploy_token``; omit to leave the file untouched.
        compile: Callable ``(src, dest) -> None`` used to compile each ``.py`` file
            to ``.mpy`` in a staging tree before syncing.  Defaults to the real
            ``mpy_cross_compile`` (requires ``mpy-cross`` installed).  Pass a fake
            for unit tests.  When ``None`` the real compiler is used.
        use_source: When True, skip compilation entirely and sync raw ``.py`` files
            directly from the source tree.  Requires no ``mpy-cross`` toolchain.

    The list's ``boot.py`` entry, if any, is copied to the mount alongside
    ``code.py`` whenever *example_file* is given -- the
    same force-always, never-pruned handling ``code.py`` gets, since a mount's
    existing ``boot.py`` is otherwise indistinguishable from a stale one (#930).
    It is not deployed when *example_file* is ``None`` (module-only sync).
    """
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
    listed = ship_list(source_root)
    entries = listed.modules

    if use_source:
        synced = {entry.source_device: source_root / entry.source for entry in entries}
    else:
        if compile is None:
            compile = mpy_cross_compile

        validation_mount = None if dry_run else mount
        try:
            validate_mpy_cross_version(mount=validation_mount)
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
        synced = {entry.device: staging_root / entry.device for entry in entries}

    if scene is not None and not dry_run:
        _write_scene(mount, scene)

    copied: list[Path] = []
    skipped: list[Path] = []
    pruned: list[Path] = []

    if example_file is not None:
        _sync_file(example_file, mount / "code.py", "code.py", copied, skipped, dry_run, force=True)

        boot = listed.boot
        if boot is not None:
            _sync_file(
                source_root / boot.source,
                mount / boot.device,
                str(boot.device),
                copied,
                skipped,
                dry_run,
                force=True,
            )

    for device, src in synced.items():
        _sync_file(src, mount / device, str(device), copied, skipped, dry_run)

    for rel in governed_mount_files(mount, use_source):
        if rel in synced:
            continue
        pruned.append(mount / rel)
        if dry_run:
            print(f"[DRY RUN] PRUNE  {rel}")
        else:
            (mount / rel).unlink()
            print(f"PRUNE  {rel}")

    if not dry_run:
        for module in MODULE_DIRS:
            _remove_empty_dirs(mount / module)

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
        default=Path(DEFAULT_MOUNT),
        help=f"Path to the mounted CIRCUITPY volume (default: {DEFAULT_MOUNT}).",
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
            "Scene name to record as default_scene in aura-boot.json on the mounted "
            "volume, with a fresh scene_deploy_token so the next boot boots this scene "
            "over any Persisted scene on the card. Combines deploying code "
            "and selecting the game into one step. Omit to leave any existing "
            "aura-boot.json untouched."
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
