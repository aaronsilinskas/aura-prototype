"""Static guard: hardware/shared imports no device-only library.

``hardware/shared`` is the board-free half of the hardware layer -- the whole
point of the ``engine ↔ hardware`` split the `import-linter` contracts in
``pyproject.toml`` enforce is that ``hardware/shared`` stays importable and
testable under plain CPython. Those contracts are first-party-to-first-party
(``engine`` must not import ``hardware``, etc.); `import-linter`'s
``forbidden`` contract can name individual external modules too, but not a
whole family sharing an ``adafruit_`` prefix (each chip ships its own PyPI
name), so it cannot express this seam. This module parses every top-level
``hardware/shared`` module with ``ast`` instead, mirroring
``scripts/tests/test_profiler_import_guard.py``'s approach, and asserts none
of them imports ``board``, ``busio``, ``pulseio``, ``digitalio``,
``microcontroller``, or any ``adafruit_*`` package -- except
``profiler_report.board_id``'s own defensive ``board`` import, which reads
board identity for a report header, not to construct hardware (#725).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARDWARE_SHARED_DIR = _REPO_ROOT / "hardware" / "shared"

_FORBIDDEN_ROOTS = frozenset({"board", "busio", "pulseio", "digitalio", "microcontroller"})

_CARVE_OUT_MODULE = "profiler_report.py"
_CARVE_OUT_FUNCTION = "board_id"


def is_forbidden_root(name: str) -> bool:
    """Whether *name* is a module root this guard forbids under hardware/shared.

    Exact match for the on-device buses/pins (``board``, ``busio``,
    ``pulseio``, ``digitalio``, ``microcontroller``); any ``adafruit_``-
    prefixed name matches too, since Adafruit ships one PyPI package per chip
    rather than a single importable family.
    """
    return name in _FORBIDDEN_ROOTS or name.startswith("adafruit_")


def board_id_carve_out_lines(source: str) -> set[int]:
    """Line numbers spanned by a top-level ``board_id`` function's body, if any.

    The only carve-out this guard grants: a module's ``board_id`` function is
    allowed its own defensive ``board`` import. Callers apply this only to
    ``profiler_report.py`` -- every other module gets no carve-out even if
    it happened to define a same-named function.
    """
    lines: set[int] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == _CARVE_OUT_FUNCTION:
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def forbidden_imports(source: str, carve_out_lines: frozenset[int] = frozenset()) -> list[str]:
    """Dotted names of every forbidden-root import in *source*.

    Walks the whole tree so an import nested inside a function (e.g. a
    deferred device-library import) is caught alongside a module-level one.
    An import whose line number falls in *carve_out_lines* is skipped --
    the one seam this guard grants, via :func:`board_id_carve_out_lines`.
    """
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if is_forbidden_root(root) and node.lineno not in carve_out_lines:
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if is_forbidden_root(root) and node.lineno not in carve_out_lines:
                violations.append(node.module)
    return violations


def _shared_module_paths() -> list[Path]:
    return sorted(_HARDWARE_SHARED_DIR.glob("*.py"))


# ---------------------------------------------------------------------------
# is_forbidden_root
# ---------------------------------------------------------------------------


def test_is_forbidden_root_matches_each_exact_device_only_name() -> None:
    for name in ("board", "busio", "pulseio", "digitalio", "microcontroller"):
        assert is_forbidden_root(name), f"{name} should be forbidden"


def test_is_forbidden_root_matches_any_adafruit_prefixed_name() -> None:
    assert is_forbidden_root("adafruit_drv2605")
    assert is_forbidden_root("adafruit_is31fl3741")


def test_is_forbidden_root_excludes_first_party_and_stdlib_names() -> None:
    assert not is_forbidden_root("engine")
    assert not is_forbidden_root("hardware")
    assert not is_forbidden_root("sys")


# ---------------------------------------------------------------------------
# board_id_carve_out_lines
# ---------------------------------------------------------------------------


def test_board_id_carve_out_lines_covers_the_functions_body() -> None:
    source = "def board_id():\n    import board\n    return board.board_id\n"

    lines = board_id_carve_out_lines(source)

    assert 2 in lines


def test_board_id_carve_out_lines_empty_when_no_board_id_function_defined() -> None:
    source = "def other():\n    import board\n    return board\n"

    assert board_id_carve_out_lines(source) == set()


# ---------------------------------------------------------------------------
# forbidden_imports
# ---------------------------------------------------------------------------


def test_forbidden_imports_collects_a_plain_import() -> None:
    assert forbidden_imports("import board\n") == ["board"]


def test_forbidden_imports_collects_a_from_import() -> None:
    source = "from adafruit_drv2605 import DRV2605\n"

    assert forbidden_imports(source) == ["adafruit_drv2605"]


def test_forbidden_imports_ignores_first_party_and_stdlib_imports() -> None:
    source = "import sys\nfrom engine.network import LINE\n"

    assert forbidden_imports(source) == []


def test_forbidden_imports_collects_import_nested_inside_a_function() -> None:
    source = "def build():\n    import busio\n    return busio\n"

    assert forbidden_imports(source) == ["busio"]


def test_forbidden_imports_skips_a_line_in_carve_out_lines() -> None:
    source = "import board\n"

    assert forbidden_imports(source, carve_out_lines=frozenset({1})) == []


def test_forbidden_imports_still_flags_a_forbidden_import_outside_carve_out_lines() -> None:
    source = "import os\nimport board\n"

    assert forbidden_imports(source, carve_out_lines=frozenset({1})) == ["board"]


# ---------------------------------------------------------------------------
# Guard: no hardware/shared module imports a device-only library, except
# profiler_report.board_id's own board import
# ---------------------------------------------------------------------------


def test_hardware_shared_modules_are_discovered() -> None:
    assert _shared_module_paths(), f"no modules found under {_HARDWARE_SHARED_DIR}"


@pytest.mark.parametrize("path", _shared_module_paths(), ids=lambda p: p.name)
def test_hardware_shared_module_has_no_forbidden_import(path: Path) -> None:
    source = path.read_text()
    carve_out = (
        frozenset(board_id_carve_out_lines(source))
        if path.name == _CARVE_OUT_MODULE
        else frozenset()
    )

    violations = forbidden_imports(source, carve_out_lines=carve_out)

    assert not violations, (
        f"{path.name} imports device-only module(s) {violations} -- hardware/shared must stay "
        "board-free except profiler_report.board_id's own board import"
    )


def test_profiler_report_board_import_outside_board_id_is_still_flagged() -> None:
    """The carve-out is scoped to board_id's own body -- a hypothetical board
    import elsewhere in profiler_report.py is not swept in with it."""
    source = "def board_id():\n    import board\n    return board\n\nimport board\n"
    carve_out = frozenset(board_id_carve_out_lines(source))

    violations = forbidden_imports(source, carve_out_lines=carve_out)

    assert violations == ["board"]
