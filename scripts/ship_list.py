"""The Ship list: which repo files go on the device, and where each lands.

Host-only (CPython). The build and deploy steps both follow it, so neither
keeps exclusion or placement rules of its own. ``code.py`` is not in it: deploy
takes the example to ship as ``code.py`` as an argument.
"""

from pathlib import Path
from typing import Final, NamedTuple

# Repo-relative directories whose contents ship, each to the same path on the mount.
MODULE_DIRS: Final = (
    "app",
    "effects",
    "engine",
    "hardware/circuitpython",
    "hardware/shared",
    "magic",
    "packs",
)

# The board's boot.py sits among the CircuitPython drivers but must land on the
# mount root; CircuitPython only runs it from there.
_BOOT_SOURCE: Final = Path("hardware/circuitpython/boot.py")
_BOOT_DEVICE: Final = Path("boot.py")

_EXCLUDED_DIR_NAMES: Final = frozenset({"__pycache__", "tests"})
_EXCLUDED_FILE_NAMES: Final = frozenset({"conftest.py"})
# The Simulation test harness and the Simulated device are test-only. Matched by
# path, not name, so a shipped package that shares either name still ships.
_TEST_ONLY_PATHS: Final = (Path("app/simulation"), Path("hardware/simulated"))

_COMPILED_SUFFIX: Final = ".py"
_COMPILED_TARGET_SUFFIX: Final = ".mpy"
_RAW_SUFFIXES: Final = frozenset({".json", ".txt", ".wav"})


class ShipEntry(NamedTuple):
    """One file that ships, with paths relative to the source root and the mount root."""

    source: Path
    device: Path
    """Where the file lands on a compiled deploy: the ``.mpy`` path when compiled."""
    compiled: bool

    @property
    def source_device(self) -> Path:
        """Where the file lands when deployed as source, compiling nothing."""
        return self.device.with_suffix(_COMPILED_SUFFIX) if self.compiled else self.device


class ShipList(NamedTuple):
    """Every file that ships from one source tree."""

    modules: list[ShipEntry]
    """Files that land at their repo path under a module directory, sorted by source path."""
    boot: ShipEntry | None
    """The board's ``boot.py``, landing on the mount root; None when the tree has none."""


def ship_list(source_root: Path) -> ShipList:
    """Return the Ship list of the source tree at *source_root*."""
    modules: dict[Path, ShipEntry] = {}
    for module in MODULE_DIRS:
        for init in _parent_inits(source_root, Path(module)):
            modules[init] = _module_entry(init)
        for src in (source_root / module).rglob("*"):
            rel = src.relative_to(source_root)
            if src.is_file() and not _is_excluded(rel) and _ships(rel):
                modules[rel] = _module_entry(rel)
    boot = None
    if (source_root / _BOOT_SOURCE).is_file():
        boot = ShipEntry(_BOOT_SOURCE, _BOOT_DEVICE, compiled=False)
    return ShipList(sorted(modules.values()), boot)


def governed_mount_files(mount: Path) -> list[Path]:
    """Return the mount-relative files under *mount*'s module directories the list governs.

    A governed file is one of a kind the list ships (or the ``.mpy`` a compiled
    deploy leaves) outside its exclusions. Deploy prunes each governed file the
    list doesn't name, and leaves every other file on the mount alone.
    """
    governed = []
    for module in MODULE_DIRS:
        for path in sorted((mount / module).rglob("*")):
            rel = path.relative_to(mount)
            if path.is_file() and _is_governed(rel):
                governed.append(rel)
    return governed


def _is_governed(rel: Path) -> bool:
    return not _is_excluded(rel) and (_ships(rel) or rel.suffix == _COMPILED_TARGET_SUFFIX)


def _parent_inits(source_root: Path, module: Path) -> list[Path]:
    """Return the existing ``__init__.py`` of each package above a nested *module*."""
    parents = [Path(*module.parts[: i + 1]) for i in range(len(module.parts) - 1)]
    inits = [parent / "__init__.py" for parent in parents]
    return [init for init in inits if (source_root / init).is_file()]


def _is_excluded(rel: Path) -> bool:
    return (
        rel == _BOOT_SOURCE
        or rel.name in _EXCLUDED_FILE_NAMES
        or any(part in _EXCLUDED_DIR_NAMES for part in rel.parts)
        or any(rel.is_relative_to(path) for path in _TEST_ONLY_PATHS)
    )


def _ships(rel: Path) -> bool:
    return rel.suffix == _COMPILED_SUFFIX or rel.suffix in _RAW_SUFFIXES


def _module_entry(rel: Path) -> ShipEntry:
    if rel.suffix == _COMPILED_SUFFIX:
        return ShipEntry(rel, rel.with_suffix(_COMPILED_TARGET_SUFFIX), compiled=True)
    return ShipEntry(rel, rel, compiled=False)
