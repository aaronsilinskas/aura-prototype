"""Static guard: the Scene boot contract forbids every library hardware/circuitpython imports.

Each library missing from that contract's ``forbidden_modules`` in
``pyproject.toml`` is one the Scene boot could import unchecked.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CIRCUITPYTHON_DIR = _REPO_ROOT / "hardware" / "circuitpython"
_CONTRACT_NAME = "the Scene boot must not import board-only hardware"
_SAMPLE_ROOT_PACKAGES = frozenset({"engine", "hardware"})


def external_imports(source: str, first_party: Iterable[str]) -> set[str]:
    """Top-level names of the modules *source* imports from outside the repo and the stdlib."""
    excluded = set(first_party) | set(sys.stdlib_module_names)
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots - excluded


def contract_drift(imported: set[str], forbidden: set[str]) -> list[str]:
    """What to change in the contract's ``forbidden_modules`` so it matches *imported*."""
    drift: list[str] = []
    if missing := sorted(imported - forbidden):
        drift.append(f"add to forbidden_modules: {', '.join(missing)}")
    if unused := sorted(forbidden - imported):
        drift.append(f"remove from forbidden_modules: {', '.join(unused)}")
    return drift


def test_external_imports_names_the_top_level_module_of_each_board_library() -> None:
    source = "import adafruit_rfm69\nfrom adafruit_is31fl3741.adafruit_rgbmatrixqt import X\n"

    assert external_imports(source, _SAMPLE_ROOT_PACKAGES) == {
        "adafruit_rfm69",
        "adafruit_is31fl3741",
    }


def test_external_imports_counts_imports_nested_in_functions() -> None:
    source = "def build():\n    import neopixel\n"

    assert external_imports(source, _SAMPLE_ROOT_PACKAGES) == {"neopixel"}


def test_external_imports_ignores_stdlib_imports() -> None:
    source = "from __future__ import annotations\nimport sys\nfrom array import array\n"

    assert external_imports(source, _SAMPLE_ROOT_PACKAGES) == set()


def test_external_imports_ignores_imports_from_the_repos_own_packages() -> None:
    source = "from hardware.shared.device_parts import DeviceParts\nfrom engine.log import Logger\n"

    assert external_imports(source, _SAMPLE_ROOT_PACKAGES) == set()


def test_external_imports_ignores_relative_imports() -> None:
    source = "from . import sibling\nfrom .sibling import thing\n"

    assert external_imports(source, _SAMPLE_ROOT_PACKAGES) == set()


def test_contract_drift_names_an_imported_module_the_contract_misses_as_one_to_add() -> None:
    assert contract_drift({"board", "adafruit_bno055"}, {"board"}) == [
        "add to forbidden_modules: adafruit_bno055"
    ]


def test_contract_drift_names_a_forbidden_module_nothing_imports_as_one_to_remove() -> None:
    assert contract_drift({"board"}, {"board", "adafruit_rfm69"}) == [
        "remove from forbidden_modules: adafruit_rfm69"
    ]


def test_scene_boot_contract_forbids_exactly_the_libraries_hardware_circuitpython_imports() -> None:
    config = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())["tool"]["importlinter"]
    first_party = set(config["root_packages"])
    contracts = [c for c in config["contracts"] if c["name"] == _CONTRACT_NAME]
    assert len(contracts) == 1, f"pyproject.toml has no contract named {_CONTRACT_NAME!r}"
    forbidden = {
        module
        for module in contracts[0]["forbidden_modules"]
        if module.split(".")[0] not in first_party
    }
    imported: set[str] = set()
    for path in _CIRCUITPYTHON_DIR.rglob("*.py"):
        if "tests" not in path.relative_to(_CIRCUITPYTHON_DIR).parts:
            imported |= external_imports(path.read_text(), first_party)

    drift = contract_drift(imported, forbidden)

    assert not drift, f"{_CONTRACT_NAME!r} in pyproject.toml is out of step: " + "; ".join(drift)
