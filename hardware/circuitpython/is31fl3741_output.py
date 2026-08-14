"""EffectOutput for the IS31FL3741 13x9 RGB LED matrix.

Board-free and importable under CPython: no vendor driver or ``board``
import. The injected ``matrix`` need only satisfy the duck-type contract the
constructor and ``flush`` reach through: indexed byte writes
(``matrix[offset] = byte``) and ``matrix.show()``. ``device_builder`` owns
the real vendor import and driver construction and injects the built driver
here.
"""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from array import array

from effects.effect import PixelBuffer
from engine.state import Scope
from hardware.shared.matrix_output import MatrixEffectOutput

IS31FL3741_COLS: Final = 13

IS31FL3741_SCOPE_ROWS: Final = {
    "global.buff": range(0, 1),
    "global.debuff": range(1, 2),
    "global.main": range(2, 5),
    "personal": range(5, 7),
    "directional": range(7, 8),
    "ambient": range(8, 9),
}


def build_offset_table(rowmap: list[int], cols: int) -> array[int]:
    """Precompute each pixel-channel's driver register offset.

    The IS31FL3741 does not map a logical row/column grid to contiguous,
    uniformly ordered driver registers: columns 0-9 and 10-12 occupy
    separate address banks (the ``x < 10`` vs ``x >= 10`` split below), and
    each LED's R/B channel order flips with column parity (and again at
    column 12). This is the chip's own register contract, not general
    geometry, so it stays in this module rather than the shared matrix base.

    *rowmap* maps each logical row to its physical driver row (panel rows
    are not wired top-to-bottom in order); *cols* is the column count.

    Returns a flat ``array("H", ...)`` of length ``len(rowmap) * cols * 3``,
    one ``(b_off, g_off, r_off)`` register-offset triple per pixel, indexed
    as ``(row * cols + x) * 3``. Calling this once at construction lets the
    per-frame write be a flat indexed copy with no addressing math.
    """
    num_rows = len(rowmap)
    offsets: array[int] = array("H", [0] * (num_rows * cols * 3))
    for row in range(num_rows):
        y = rowmap[row]
        for x in range(cols):
            base = 3 * (x + y * 10 if x < 10 else x + 80 + y * 3)
            if x & 1 or x == 12:
                b_off, g_off, r_off = base + 1, base, base + 2
            else:
                b_off, g_off, r_off = base + 2, base + 1, base
            idx = (row * cols + x) * 3
            offsets[idx] = b_off
            offsets[idx + 1] = g_off
            offsets[idx + 2] = r_off
    return offsets


class IS31FL3741EffectOutput(MatrixEffectOutput):
    """EffectOutput for the IS31FL3741 13×9 RGB LED matrix."""

    __slots__ = ("_offsets",)

    # Logical row -> physical driver row: the panel's rows are not wired in
    # natural top-to-bottom order.
    _rowmap: Final = [8, 5, 4, 3, 2, 1, 0, 7, 6]

    def __init__(self, matrix: object, *, cols: int, scope_rows: dict[str, range]) -> None:
        super().__init__(cols, scope_rows)
        self.scopes = [Scope.ALL]
        self._matrix = matrix
        self._offsets: array[int] = build_offset_table(self._rowmap, cols)

    def _write_row(self, row: int, pixels: PixelBuffer) -> None:
        offsets = self._offsets
        matrix = self._matrix
        base = row * self._cols * 3
        for x in range(self._cols):
            i = base + x * 3
            color = pixels[x]
            matrix[offsets[i]] = (color >> 16) & 0xFF
            matrix[offsets[i + 1]] = (color >> 8) & 0xFF
            matrix[offsets[i + 2]] = color & 0xFF

    def flush(self) -> None:
        self._matrix.show()
