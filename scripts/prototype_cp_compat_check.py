"""PROTOTYPE (#961), throwaway: the cheapest credible CircuitPython compatibility check.

Runs three static checks over every module the deploy would ship
(``scripts.deploy.MODULE_DIRS`` minus tests) and prints what each found and
how long it took:

1. imports  -- every unguarded non-first-party import must be on a
               CircuitPython allowlist (core modules + bundled libraries).
               Imports inside ``try: ... except ImportError`` are exempt.
2. resolve  -- every first-party import (``from engine.x import y``) must
               resolve to a file on disk (generalises the profiler guard
               from #564 to all deployed code).
3. compile  -- ``tools/mpy-cross`` compiles every module (what deploy
               already does, just earlier).

Usage:
    python scripts/prototype_cp_compat_check.py            # check the working tree
    python scripts/prototype_cp_compat_check.py --rev REV  # check a past commit
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MPY_CROSS = REPO / "tools" / "mpy-cross"
MODULE_DIRS = [
    "app",
    "effects",
    "engine",
    "hardware/circuitpython",
    "hardware/shared",
    "magic",
    "packs",
    "rules",
]

# CircuitPython 10 core modules (RP2040/RP2350 builds). Hand-written for the
# prototype; a real check would capture help("modules") from the device once.
CP_CORE = {
    "__future__", "array", "binascii", "builtins", "collections", "errno", "gc",
    "io", "json", "math", "os", "random", "re", "select", "struct", "sys",
    "time", "traceback", "zlib", "hashlib", "asyncio", "micropython",
    "analogio", "audiobusio", "audiocore", "audiomixer", "audiopwmio", "bitbangio",
    "board", "busio", "countio", "digitalio", "displayio", "keypad",
    "microcontroller", "neopixel_write", "pulseio", "pwmio", "rp2pio", "rtc",
    "sdcardio", "storage", "supervisor", "usb_cdc",
}  # fmt: skip
# Libraries copied into the device's lib/ folder.
BUNDLED_LIBS = {
    "adafruit_drv2605", "adafruit_is31fl3741", "adafruit_lis3dh", "adafruit_mmc56x3",
    "adafruit_pioasm", "adafruit_rfm69", "neopixel",
}  # fmt: skip


def deployed_modules(root: Path) -> list[Path]:
    files = []
    for d in MODULE_DIRS:
        for f in sorted((root / d).rglob("*.py")):
            rel = f.relative_to(root)
            if "tests" in rel.parts or "__pycache__" in rel.parts:
                continue
            if f.name in ("conftest.py", "boot.py"):
                continue
            files.append(f)
    return files


def _guarded_node_ids(tree: ast.AST) -> set[int]:
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if any(h.type is not None and "ImportError" in ast.unparse(h.type) for h in node.handlers):
            for stmt in node.body:
                guarded.update(id(n) for n in ast.walk(stmt))
    return guarded


def check_imports(root: Path, files: list[Path]) -> list[str]:
    first_party = {p.name for p in root.iterdir() if (p / "__init__.py").exists()}
    allowed = CP_CORE | BUNDLED_LIBS | first_party
    problems = []
    for f in files:
        tree = ast.parse(f.read_text(), str(f))
        guarded = _guarded_node_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name.split(".")[0] not in allowed and id(node) not in guarded:
                    rel = f.relative_to(root)
                    problems.append(f"{rel}:{node.lineno}: '{name}' not on CircuitPython")
    return problems


def check_first_party_resolves(root: Path, files: list[Path]) -> list[str]:
    first_party = {p.name for p in root.iterdir() if (p / "__init__.py").exists()}
    problems = []
    for f in files:
        tree = ast.parse(f.read_text(), str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name.split(".")[0] not in first_party:
                    continue
                target = root.joinpath(*name.split("."))
                if not (target.with_suffix(".py").exists() or (target / "__init__.py").exists()):
                    rel = f.relative_to(root)
                    problems.append(f"{rel}:{node.lineno}: first-party '{name}' does not exist")
    return problems


def check_compiles(root: Path, files: list[Path]) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as out:
        for i, f in enumerate(files):
            result = subprocess.run(
                [str(MPY_CROSS), str(f), "-o", f"{out}/{i}.mpy"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                rel = f.relative_to(root)
                problems.append(f"{rel}: mpy-cross: {result.stderr.strip().splitlines()[-1]}")
    return problems


def run(root: Path) -> int:
    files = deployed_modules(root)
    print(f"{len(files)} deployed modules under {root}\n")
    failed = 0
    for label, check in [
        ("imports", check_imports),
        ("resolve", check_first_party_resolves),
        ("compile", check_compiles),
    ]:
        start = time.perf_counter()
        problems = check(root, files)
        took = time.perf_counter() - start
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"[{label:8}] {status:14} {took * 1000:7.0f} ms")
        for p in problems:
            print(f"    {p}")
        failed += len(problems)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rev", help="check the tree at this git revision instead")
    args = parser.parse_args()
    if args.rev is None:
        return run(REPO)
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(
            ["git", "archive", args.rev], cwd=REPO, capture_output=True, check=True
        )
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        print(f"checking {args.rev}")
        return run(Path(tmp))


if __name__ == "__main__":
    sys.exit(main())
