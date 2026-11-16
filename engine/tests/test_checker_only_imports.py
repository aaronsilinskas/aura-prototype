"""Static guard: production code imports checker-only modules only under ``TYPE_CHECKING``.

``docs/standards/embedded-python.md`` sanctions one checker-only import idiom, a
bare module-level ``TYPE_CHECKING = False`` and an ``if TYPE_CHECKING:`` block.
This guard parses every production module (every ``.py`` file outside hidden
directories, ``tests/`` directories and ``conftest.py``) and fails on the old
``try: from typing import ...`` / ``except ImportError`` form, naming each
offending file and line. ``collections.abc`` counts too: the device lacks it, so
its imports are checker-only as well.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKER_ONLY_MODULES = frozenset({"typing", "collections.abc"})


def checker_only_imports_in_try(source: str) -> list[int]:
    """Line numbers of every ``typing`` or ``collections.abc`` import inside a ``try:`` body."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Try):
            continue
        for inner in node.body:
            for statement in ast.walk(inner):
                if isinstance(statement, (ast.Import, ast.ImportFrom)) and (
                    _CHECKER_ONLY_MODULES.intersection(_imported_modules(statement))
                ):
                    lines.append(statement.lineno)
    return sorted(lines)


def _imported_modules(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    return [alias.name for alias in node.names]


def _production_modules() -> list[Path]:
    modules = []
    for path in _REPO_ROOT.rglob("*.py"):
        parts = path.relative_to(_REPO_ROOT).parts
        if path.name == "conftest.py" or "tests" in parts:
            continue
        if any(part.startswith(".") for part in parts):
            continue
        modules.append(path)
    return sorted(modules)


def test_flags_a_typing_import_in_a_try_block_with_its_line() -> None:
    source = "import sys\n\ntry:\n    from typing import Final\nexcept ImportError:\n    pass\n"

    assert checker_only_imports_in_try(source) == [4]


def test_flags_a_collections_abc_import_in_a_try_block() -> None:
    source = "try:\n    from collections.abc import Callable\nexcept ImportError:\n    pass\n"

    assert checker_only_imports_in_try(source) == [2]


def test_flags_every_checker_only_import_in_one_try_block() -> None:
    source = (
        "try:\n"
        "    from collections.abc import Callable\n"
        "    import typing\n"
        "except ImportError:\n"
        "    pass\n"
    )

    assert checker_only_imports_in_try(source) == [2, 3]


def test_accepts_the_sanctioned_type_checking_idiom() -> None:
    source = (
        "TYPE_CHECKING = False\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    from typing import Final\n"
        "\n"
        "try:\n"
        "    import board\n"
        "except ImportError:\n"
        "    board = None\n"
    )

    assert checker_only_imports_in_try(source) == []


def test_no_production_module_imports_a_checker_only_module_in_a_try_block() -> None:
    offenders = [
        f"{path.relative_to(_REPO_ROOT)}:{line}"
        for path in _production_modules()
        for line in checker_only_imports_in_try(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], (
        "Import typing and collections.abc under `TYPE_CHECKING = False` / "
        "`if TYPE_CHECKING:` (docs/standards/embedded-python.md), not in a try block:\n"
        + "\n".join(offenders)
    )
