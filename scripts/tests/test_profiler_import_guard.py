"""Static guard: every first-party import in every hardware profiler resolves on disk.

The profilers under ``examples/hardware/profiling/`` run only on-device, so a
first-party import that points at a module which no longer exists (the dead
``hardware.circuitpython.propmaker`` import that silently bricked five profilers)
is invisible to the CPython suite until someone deploys. This module parses each
profiler with ``ast`` and asserts every import whose root package is one of the
repo's own top-level packages resolves to a real module file on disk. Device and
library imports (``board``, ``adafruit_*``, stdlib) have non-first-party roots and
are excluded by construction, so they never false-positive.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFILING_DIR = _REPO_ROOT / "examples" / "hardware" / "profiling"


def first_party_packages(repo_root: Path) -> set[str]:
    """Repo-root package names — directories holding an ``__init__.py``.

    Derived from the tree rather than a hard-coded list so a renamed or new
    top-level package is covered without touching this guard.
    """
    return {
        child.name
        for child in repo_root.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    }


def first_party_import_targets(source: str, first_party: set[str]) -> list[str]:
    """Dotted module targets imported from a first-party root, anywhere in ``source``.

    Walks the whole tree so lazy imports nested inside functions are collected
    alongside module-level ones. For ``from a.b import c`` the target is the
    ``a.b`` module being imported from; relative imports have no first-party root
    and are skipped.
    """
    candidates: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            candidates.append(node.module)
    return [name for name in candidates if name.split(".")[0] in first_party]


def resolves_on_disk(dotted: str, repo_root: Path) -> bool:
    """Whether ``dotted`` maps to a module file or package under ``repo_root``."""
    base = repo_root / Path(*dotted.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


def _profiler_paths() -> list[Path]:
    return sorted(_PROFILING_DIR.glob("*.py"))


# ---------------------------------------------------------------------------
# first_party_packages
# ---------------------------------------------------------------------------


def test_first_party_packages_includes_directory_with_init_py(tmp_path: Path) -> None:
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "__init__.py").touch()

    assert "engine" in first_party_packages(tmp_path)


def test_first_party_packages_excludes_directory_without_init_py(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()

    assert "examples" not in first_party_packages(tmp_path)


# ---------------------------------------------------------------------------
# first_party_import_targets
# ---------------------------------------------------------------------------


def test_collects_module_level_first_party_from_import() -> None:
    source = "from engine.network import LINE\n"

    assert first_party_import_targets(source, {"engine"}) == ["engine.network"]


def test_excludes_device_and_stdlib_imports() -> None:
    source = "import board\nimport time\nfrom adafruit_bus_device import i2c_device\n"

    assert first_party_import_targets(source, {"engine", "hardware"}) == []


def test_collects_import_nested_inside_function() -> None:
    source = (
        "def build():\n"
        "    from hardware.circuitpython.device_builder import build_hardware\n"
        "    return build_hardware\n"
    )

    assert first_party_import_targets(source, {"hardware"}) == [
        "hardware.circuitpython.device_builder"
    ]


def test_collects_plain_import_of_first_party_module() -> None:
    source = "import engine.network as net\n"

    assert first_party_import_targets(source, {"engine"}) == ["engine.network"]


# ---------------------------------------------------------------------------
# resolves_on_disk
# ---------------------------------------------------------------------------


def test_resolves_existing_module_to_file() -> None:
    assert resolves_on_disk("engine.network", _REPO_ROOT)


def test_resolves_package_to_its_init_py() -> None:
    assert resolves_on_disk("hardware.circuitpython", _REPO_ROOT)


def test_unresolved_module_does_not_resolve() -> None:
    assert not resolves_on_disk("hardware.circuitpython.propmaker", _REPO_ROOT)


# ---------------------------------------------------------------------------
# Guard: every first-party import in every profiler resolves on disk
# ---------------------------------------------------------------------------


def test_profilers_are_discovered() -> None:
    assert _profiler_paths(), f"no profilers found under {_PROFILING_DIR}"


@pytest.mark.parametrize("profiler", _profiler_paths(), ids=lambda path: path.name)
def test_every_first_party_import_resolves_on_disk(profiler: Path) -> None:
    first_party = first_party_packages(_REPO_ROOT)

    targets = first_party_import_targets(profiler.read_text(), first_party)
    unresolved = [t for t in targets if not resolves_on_disk(t, _REPO_ROOT)]

    assert not unresolved, f"{profiler.name} imports missing first-party modules: {unresolved}"
