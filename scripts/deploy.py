"""Deploy a CircuitPython example and module directories to a mounted CIRCUITPY volume.

Usage
-----
    # Deploy an example and sync all modules:
    python scripts/deploy.py examples/effects/propmaker_demo.py

    # Sync modules only, without changing code.py:
    python scripts/deploy.py

    # Override the default mount path:
    python scripts/deploy.py examples/effects/propmaker_demo.py --mount /Volumes/MYBOARD
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from typing import Final
except ImportError:
    pass

MODULE_DIRS: "Final" = ["effects", "engine", "magic", "rules"]
_EXCLUDE_DIRS: "Final" = {"__pycache__"}
_EXCLUDE_SUFFIXES: "Final" = {".pyc", ".mpy"}
_DEFAULT_MOUNT: "Final" = "/Volumes/CIRCUITPY"


def _is_excluded(rel: Path) -> bool:
    """Return True if a relative path should be excluded from sync."""
    for part in rel.parts:
        if part in _EXCLUDE_DIRS:
            return True
    return rel.suffix in _EXCLUDE_SUFFIXES


def _should_skip(dest: Path) -> bool:
    """Return True if the destination file is already up to date.

    Slice 1: skip whenever the destination already exists.
    Slice 2 will refine this with FAT32-aware mtime comparison.
    """
    return dest.exists()


def _sync_file(
    src: Path,
    dest: Path,
    label: str,
    copied: "list[Path]",
    skipped: "list[Path]",
    dry_run: bool = False,
) -> None:
    """Copy src to dest unless it should be skipped."""
    if _should_skip(dest):
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


def deploy(
    example_file: "Path | None",
    mount: Path,
    source_root: "Path | None" = None,
    dry_run: bool = False,
) -> int:
    """Deploy to mount. Returns 0 on success, 1 on error.

    Args:
        example_file: Path to the example file to copy as ``code.py``.
            Pass ``None`` to sync modules only without touching ``code.py``.
        mount: Path to the mounted CIRCUITPY volume.
        source_root: Root of the source tree. Defaults to ``Path.cwd()``.
        dry_run: When True, skip mount validation and print what would be copied
            without writing any files.
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

    if not os.access(mount, os.W_OK):
        print(
            "Error: CIRCUITPY is read-only. Press Ctrl+C on the device to stop code.py first.",
            file=sys.stderr,
        )
        return 1

    copied: list[Path] = []
    skipped: list[Path] = []

    if example_file is not None:
        _sync_file(example_file, mount / "code.py", "code.py", copied, skipped, dry_run)

    for module in MODULE_DIRS:
        src_dir = source_root / module
        if not src_dir.is_dir():
            continue
        dest_dir = mount / module
        for src_file in sorted(src_dir.rglob("*")):
            if src_file.is_dir():
                continue
            rel = src_file.relative_to(src_dir)
            if _is_excluded(rel):
                continue
            label = f"{module}/{rel}"
            _sync_file(src_file, dest_dir / rel, label, copied, skipped, dry_run)

    print(f"Done. {len(copied)} copied, {len(skipped)} skipped.")
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
    args = parser.parse_args()
    sys.exit(deploy(args.example_file, args.mount, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
