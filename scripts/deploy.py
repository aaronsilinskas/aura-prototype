"""Deploy a CircuitPython example and module directories to a mounted CIRCUITPY volume.

Usage
-----
    # Deploy an example and sync all modules (compiles .py → .mpy via mpy-cross):
    uv run python scripts/deploy.py examples/hardware/scene_demo.py

    # Sync modules only, without changing code.py:
    uv run python scripts/deploy.py

    # Override the default mount path:
    uv run python scripts/deploy.py examples/hardware/scene_demo.py --mount /Volumes/MYBOARD

mpy-cross
---------
Compiling needs the CircuitPython ``mpy-cross`` binary that
``scripts/setup_mpy_cross.sh`` downloads; ``scripts/build.py`` says where it
is looked up.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

if not __package__:
    # Run as a file (uv run python scripts/deploy.py): put the repo root on the path so
    # the package imports below resolve as they do under python -m.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.shared.scene_selection import with_scene_deploy
from scripts.build import BuildError, MpyCross, Toolchain, VersionError, build
from scripts.ship_list import MODULE_DIRS, governed_mount_files, ship_list

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Final

DEFAULT_MOUNT: Final = "/Volumes/CIRCUITPY"


class DeployError(Exception):
    """A deploy was refused or failed before anything was written to the mount.

    The message is the line a user sees after ``Error:``. A version mismatch or
    compile failure is raised from the build module's error.
    """


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
    copied: list[Path],
    skipped: list[Path],
    dry_run: bool = False,
    force: bool = False,
) -> None:
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
    if not dest_dir.is_dir():
        return
    for d in sorted(dest_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    if not any(dest_dir.iterdir()):
        dest_dir.rmdir()


def _write_scene(mount: Path, scene: str) -> None:
    """Set ``default_scene`` and a fresh Scene deploy token in ``aura-boot.json``.

    Merges with any existing keys, creating the file when the board has none.
    """
    boot_path = mount / "aura-boot.json"
    boot_values = json.loads(boot_path.read_text()) if boot_path.exists() else {}
    boot_values = with_scene_deploy(boot_values, scene, secrets.token_hex(8))
    boot_path.write_text(json.dumps(boot_values, indent=2))


@dataclass(frozen=True)
class CompiledBuild:
    """Modules ship as ``.mpy`` files that *toolchain* compiles."""

    toolchain: Toolchain


@dataclass(frozen=True)
class SourceBuild:
    """Modules ship as raw ``.py`` files, so no compiler is involved."""


@dataclass(frozen=True)
class DeployPlan:
    """One deploy, validated against the mount as it was when planned."""

    example_file: Path | None
    mount: Path
    source_root: Path
    scene: str | None
    dry_run: bool
    build_choice: CompiledBuild | SourceBuild


def plan_deploy(
    example_file: Path | None,
    mount: Path,
    source_root: Path,
    *,
    toolchain: Toolchain,
    scene: str | None = None,
    dry_run: bool = False,
    use_source: bool = False,
) -> DeployPlan:
    """Validate a deploy and return its plan.

    Args:
        example_file: The example to deploy as ``code.py``, or ``None`` to sync
            modules only.
        mount: The mounted CIRCUITPY volume.
        source_root: Root of the source tree the Ship list is read from.
        toolchain: Compiles modules, and checks its version against *mount*
            (or, for a dry run, the repo-pinned CircuitPython major). A source
            deploy never uses it.
        scene: Scene to record as ``default_scene`` in ``aura-boot.json``,
            beside a fresh Scene deploy token; ``None`` leaves the file alone.
        dry_run: Print what would change without writing to the mount. The
            mount checks are skipped.
        use_source: Ship raw ``.py`` files instead of compiling them.

    Raises:
        DeployError: The mount is missing, not a directory or read-only, or
            the toolchain's version doesn't match.
    """
    if not dry_run:
        if not mount.is_dir():
            raise DeployError(f"mount path '{mount}' does not exist or is not a directory.")
        if not os.access(mount, os.W_OK):
            raise DeployError(
                "CIRCUITPY is read-only. Press Ctrl+C on the device to stop code.py first."
            )

    build_choice: CompiledBuild | SourceBuild
    if use_source:
        build_choice = SourceBuild()
    else:
        try:
            toolchain.check_version(None if dry_run else mount)
        except VersionError as exc:
            raise DeployError(str(exc)) from exc
        build_choice = CompiledBuild(toolchain)

    return DeployPlan(
        example_file=example_file,
        mount=mount,
        source_root=source_root,
        scene=scene,
        dry_run=dry_run,
        build_choice=build_choice,
    )


def execute_plan(plan: DeployPlan) -> None:
    """Carry out *plan*, raising :class:`DeployError` if a module fails to compile.

    An example ships with the Ship list's ``boot.py``, force-copied and never
    pruned like ``code.py``: a ``boot.py`` already on the mount can't be told
    apart from a stale one, so it is replaced whenever ``code.py`` is.
    """
    mount = plan.mount
    source_root = plan.source_root
    dry_run = plan.dry_run
    listed = ship_list(source_root)
    entries = listed.modules

    compiled_count = 0
    build_choice = plan.build_choice
    if isinstance(build_choice, CompiledBuild):
        use_source = False
        staging_root = source_root / "build"
        try:
            build_result = build(
                source_root=source_root,
                staging_root=staging_root,
                compile=build_choice.toolchain.compile,
            )
        except BuildError as exc:
            raise DeployError(str(exc)) from exc
        compiled_count = build_result.compiled
        synced = {entry.device: staging_root / entry.device for entry in entries}
    else:
        use_source = True
        synced = {entry.source_device: source_root / entry.source for entry in entries}

    if plan.scene is not None and not dry_run:
        _write_scene(mount, plan.scene)

    copied: list[Path] = []
    skipped: list[Path] = []
    pruned: list[Path] = []

    if plan.example_file is not None:
        _sync_file(
            plan.example_file, mount / "code.py", "code.py", copied, skipped, dry_run, force=True
        )

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


def run_deploy_cli(
    example_file: Path | None,
    mount: Path,
    *,
    toolchain: Toolchain | None = None,
    scene: str | None = None,
    dry_run: bool = False,
    use_source: bool = False,
    execute: Callable[[DeployPlan], None] = execute_plan,
) -> int:
    """Plan a deploy from the current directory and *execute* it, for a command line.

    This is the command-line adapter that ``main`` and deploy-watch share, not
    part of the library surface: it returns 0, or 1 after printing the
    ``Error:`` line to stderr if the deploy is refused or fails. *toolchain*
    defaults to the real ``mpy-cross``.
    """
    try:
        plan = plan_deploy(
            example_file,
            mount,
            Path.cwd(),
            toolchain=toolchain if toolchain is not None else MpyCross(),
            scene=scene,
            dry_run=dry_run,
            use_source=use_source,
        )
        execute(plan)
    except DeployError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> None:
    """Run the deploy from the command line (``sys.argv`` when ``argv`` is ``None``).

    Exits 1 with an ``Error:`` line on stderr when the deploy fails.
    """
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
    args = parser.parse_args(argv)
    rc = run_deploy_cli(
        args.example_file,
        args.mount,
        scene=args.scene,
        dry_run=args.dry_run,
        use_source=args.source,
    )
    if rc != 0:
        sys.exit(rc)


if __name__ == "__main__":
    main()
