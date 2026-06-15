"""Shim CircuitPython-only ``gc`` heap-introspection functions for CPython tests.

``gc.mem_alloc`` and ``gc.mem_free`` exist on CircuitPython/MicroPython but not
CPython. Tests that exercise ``PerformanceTracker`` need these to be callable;
the values returned are not meaningful on CPython, only their presence.
"""

import gc

if not hasattr(gc, "mem_alloc"):
    gc.mem_alloc = lambda: 0  # type: ignore[attr-defined]

if not hasattr(gc, "mem_free"):
    gc.mem_free = lambda: 0  # type: ignore[attr-defined]
