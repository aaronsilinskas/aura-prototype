try:
    from typing import Final
except ImportError:
    pass

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

    def __init__(self, matrix: object, *, cols: int, scope_rows: dict) -> None:
        super().__init__(cols, scope_rows)
        self.scopes = [Scope.ALL]
        self._matrix = matrix

    def _write_row(self, row: int, pixels) -> None:
        for col in range(self._cols):
            self._matrix.pixel(col, row, pixels[col])

    def flush(self) -> None:
        self._matrix.show()
