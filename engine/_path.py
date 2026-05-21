"""Cross-platform path helpers compatible with CircuitPython, MicroPython, and CPython.

CircuitPython's ``os`` module exposes ``os.stat`` and ``os.listdir`` but does
not include ``os.path``.  This module provides ``normpath``, ``join``,
``isdir``, and ``isfile`` that fall back to ``os.stat``-based implementations
on constrained runtimes.
"""

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
