try:
    from typing import Final
except ImportError:
    pass

from array import array

from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

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


class IS31FL3741EffectOutput(MatrixEffectOutput):
    """EffectOutput for the IS31FL3741 13×9 RGB LED matrix.

    Subclasses ``MatrixEffectOutput``; all scope-to-row-band routing lives in
    the base class.  This subclass provides only the last-mile hardware calls:
    ``_write_row`` writes pixels via ``self._matrix.pixel(col, row, color)``
    and ``flush`` calls ``self._matrix.show()``.

    Args:
        matrix: A configured IS31FL3741 driver instance (e.g.
            ``Adafruit_RGBMatrixQT``).  Injected at construction so setup
            code remains in ``device_builder.py`` and this class stays testable.
        cols: Number of columns in the LED matrix.  Pass ``IS31FL3741_COLS``
            (13) for the standard Adafruit 13×9 board.
        scope_rows: Mapping of scope key → row-band ``range`` for this matrix.
            Pass ``IS31FL3741_SCOPE_ROWS`` for the standard aura wand layout.
    """

    rowmap: Final = [8, 5, 4, 3, 2, 1, 0, 7, 6]
    IS3741_BGR: Final = (2 << 4) | (1 << 2) | (0)  # Encode as B,G,R
    r_offset: Final = 2
    g_offset: Final = 1
    b_offset: Final = 0

    def __init__(
        self, matrix: Adafruit_RGBMatrixQT, *, cols: int, scope_rows: dict
    ) -> None:
        super().__init__(cols, scope_rows)
        self.scopes = [Scope.ALL]
        self._matrix = matrix
        num_rows = len(self.rowmap)
        offsets: array[int] = array("H", [0] * (num_rows * cols * 3))
        for row in range(num_rows):
            y = self.rowmap[row]
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
        self._offsets: array[int] = offsets

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
