from engine.state import Scope
from hardware.shared.matrix_output import MatrixEffectOutput

_MATRIX_COLS = 13

_SCOPE_ROWS = {
    "global.buff": range(0, 1),
    "global.debuff": range(1, 2),
    "global.main": range(2, 5),
    "personal": range(5, 7),
    "directional": range(7, 9),
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
            code remains in ``propmaker.py`` and this class stays testable.
    """

    def __init__(self, matrix) -> None:
        super().__init__(_MATRIX_COLS, _SCOPE_ROWS)
        self.scopes = [Scope.NON_AMBIENT]
        self._matrix = matrix

    def _write_row(self, row: int, pixels) -> None:
        for col in range(self._cols):
            self._matrix.pixel(col, row, pixels[col])

    def flush(self) -> None:
        self._matrix.show()
