from __future__ import annotations

from effects.effect import PixelBuffer
from engine.effects.manager import EffectOutput
from engine.state import EffectReceipt


class MatrixEffectOutput(EffectOutput):
    """Hardware-agnostic base class for matrix LED outputs with scope-to-row-band routing.

    Subclasses must implement ``_write_row(row, pixels)`` to perform the actual
    hardware write.  All routing logic lives here; subclasses contain only the
    last-mile hardware calls.
    """

    def __init__(self, cols: int, scope_rows: dict[str, range]) -> None:
        self.min_resolution = cols
        self._cols = cols
        self._scope_rows = scope_rows
        self._zero_buffer = PixelBuffer(cols)

    @property
    def matrix(self) -> object:
        """The underlying hardware matrix driver this output writes to.

        Read-only. Lets a caller reach the one shared driver to build further
        outputs around it (e.g. the pixel profiler sweeping row bands) without
        re-probing hardware or touching a private attribute. Subclasses set
        ``self._matrix`` to the driver they own.
        """
        return self._matrix

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        """Return a PixelBuffer sized for one row of the matrix (``cols`` pixels)."""
        return PixelBuffer(self._cols)

    def update_pixels(
        self, scope_key: str, buffers: list[PixelBuffer], receipts: list[EffectReceipt]
    ) -> None:
        """Render each buffer into the scope's row band via ``_write_row``."""
        row_band = self._scope_rows[scope_key]
        receipt = receipts[-1] if receipts else None
        brightness = receipt.brightness if receipt is not None else 1.0
        for row in row_band:
            if not buffers:
                self._write_row(row, self._zero_buffer)
                continue
            pixels = buffers[-1]
            if brightness != 1.0:
                pixels = self._scale_pixels(pixels, brightness)
            self._write_row(row, pixels)

    def _scale_pixels(self, pixels: PixelBuffer, brightness: float) -> PixelBuffer:
        scaled = PixelBuffer(self._cols)
        for i in range(self._cols):
            c = pixels[i]
            r = int(((c >> 16) & 0xFF) * brightness)
            g = int(((c >> 8) & 0xFF) * brightness)
            b = int((c & 0xFF) * brightness)
            scaled[i] = (r << 16) | (g << 8) | b
        return scaled

    def clear_pixels(self, scope_key: str) -> None:
        """Zero all rows in the scope's row band using the pre-allocated zero buffer."""
        row_band = self._scope_rows[scope_key]
        for row in row_band:
            self._write_row(row, self._zero_buffer)

    def _write_row(self, row: int, pixels: PixelBuffer) -> None:
        """Write ``pixels`` to hardware row ``row``.  Must be overridden by subclasses."""
        raise NotImplementedError
