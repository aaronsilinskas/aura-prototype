"""Tests for the host-only ``micropython`` module that stands in for the device's built-in."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import micropython

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DECORATED_MODULE = (
    "import micropython\n\n\n@micropython.native\ndef double(x: int) -> int:\n    return x * 2\n"
)


def test_native_returns_the_same_function_so_decorated_code_runs_unchanged_on_cpython() -> None:
    def blend(a: int, b: int) -> int:
        return a + b

    assert micropython.native(blend) is blend


def test_const_returns_its_argument() -> None:
    sentinel = object()

    assert micropython.const(sentinel) is sentinel


def test_a_module_decorated_with_micropython_native_imports_and_runs_on_cpython(
    tmp_path: Path,
) -> None:
    source = tmp_path / "decorated.py"
    source.write_text(_DECORATED_MODULE)
    spec = importlib.util.spec_from_file_location("decorated", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert module.double(21) == 42


def test_mypy_checks_a_micropython_native_function_with_its_own_signature(
    tmp_path: Path,
) -> None:
    # The circuitpython-stubs stub has no ``native``, so a clean run proves mypy
    # resolved ``micropython`` to the host-only module instead.
    source = tmp_path / "decorated.py"
    source.write_text(_DECORATED_MODULE + "\n\nreveal_type(double)\n")

    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--no-error-summary", str(source)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Revealed type is "def (x: int) -> int"' in result.stdout
