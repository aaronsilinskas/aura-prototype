from effects.effect import PixelBuffer
from engine.effects.manager import EffectOutput


class MatrixEffectOutput(EffectOutput):
    """Hardware-agnostic base class for matrix LED outputs with scope-to-row-band routing.

    Subclasses must implement ``_write_row(row, pixels)`` to perform the actual
    hardware write.  All routing logic lives here; subclasses contain only the
    last-mile hardware calls.
    """

    def __init__(self, cols: int, scope_rows: dict) -> None:
        self.min_resolution = cols
        self._cols = cols
        self._scope_rows = scope_rows
        self._zero_buffer = PixelBuffer(cols)

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        """Return a PixelBuffer sized for one row of the matrix (``cols`` pixels)."""
        return PixelBuffer(self._cols)

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        """Render each buffer into the scope's row band via ``_write_row``."""
        row_band = self._scope_rows[scope_key]
        for row in row_band:
            pixels = buffers[-1] if buffers else self._zero_buffer
            self._write_row(row, pixels)

    def clear_pixels(self, scope_key: str) -> None:
        """Zero all rows in the scope's row band using the pre-allocated zero buffer."""
        row_band = self._scope_rows[scope_key]
        for row in row_band:
            self._write_row(row, self._zero_buffer)

    def _write_row(self, row: int, pixels: PixelBuffer) -> None:
        """Write ``pixels`` to hardware row ``row``.  Must be overridden by subclasses."""
        raise NotImplementedError
