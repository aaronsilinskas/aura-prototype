"""Cross-platform path helpers compatible with CircuitPython, MicroPython, and CPython.

CircuitPython's ``os`` module exposes ``os.stat`` and ``os.listdir`` but does
not include ``os.path``.  This module provides ``normpath``, ``join``,
``isdir``, and ``isfile`` that fall back to ``os.stat``-based implementations
on constrained runtimes, plus ``scan_stems``, the one stem rule for files on disk.
"""

from __future__ import annotations

import os

try:
    from os.path import isdir, isfile, join, normpath
except (ImportError, AttributeError):
    # CircuitPython / MicroPython fallback.
    def normpath(p):  # type: ignore[misc]
        return p

    def join(a, b):  # type: ignore[misc]
        return a.rstrip("/") + "/" + b

    def isdir(p):  # type: ignore[misc]
        try:
            return bool(os.stat(p)[0] & 0x4000)
        except OSError:
            return False

    def isfile(p):  # type: ignore[misc]
        try:
            return bool(os.stat(p)[0] & 0x8000)
        except OSError:
            return False


def scan_stems(path: str, extensions: tuple[str, ...]) -> dict[str, str]:
    """Return a stem → file path map for files directly in *path* ending in *extensions*.

    The one stem rule for every kind on disk: pack items (``.py``/``.mpy``) and
    sounds (``.wav``). Excludes ``__init__`` and directories. A missing or
    non-directory *path* yields an empty map.
    """
    stems: dict[str, str] = {}
    if not isdir(path):
        return stems
    for fname in os.listdir(path):
        for ext in extensions:
            if fname.endswith(ext):
                stem = fname[: -len(ext)]
                break
        else:
            continue
        if stem == "__init__":
            continue
        full_path = join(path, fname)
        if isdir(full_path):
            continue
        stems[stem] = full_path
    return stems
