"""NeoPixel effect output — one strip, multiple scope segments.

The ``neopixel`` import lives only in ``device_builder`` (which supplies
already-initialised strip objects), keeping this module testable under CPython.
"""

from __future__ import annotations

from effects.effect import PixelBuffer
from engine.effects.manager import EffectOutput
from engine.state import EffectReceipt, ScopeValue

__all__ = ["NeoPixelEffectOutput"]


class NeoPixelEffectOutput(EffectOutput):
    """Routes scope-keyed pixel writes to the correct offset within a physical NeoPixel strip.

    Per-strip brightness is a hardware-init concern applied to the
    ``neopixel.NeoPixel`` object at construction (the library scales it at
    ``show()``) — this output holds no brightness of its own and only applies
    the per-effect receipt brightness.

    Args:
        strip: Strip object supporting ``strip[i] = color`` (packed RGB int)
            and ``strip.show()``.
        scope_pixels: Mapping of scope key to a ``range`` of pixel indices
            within the strip.  Must be non-empty.
    """

    __slots__ = ("_scope_pixels", "_strip", "min_resolution", "scopes")

    def __init__(
        self,
        strip: object,
        scope_pixels: dict[str, range],
    ) -> None:
        super().__init__()
        self._strip = strip
        self._scope_pixels: dict[str, range] = scope_pixels
        self.scopes: list[ScopeValue] = [ScopeValue(key) for key in scope_pixels]
        self.min_resolution: int = max(len(r) for r in scope_pixels.values())

    @property
    def strip(self) -> object:
        """The underlying hardware NeoPixel strip this output writes to.

        Read-only. Lets a caller reach the one shared strip to build further
        outputs around it (e.g. the pixel profiler sweeping segment lengths)
        without re-constructing the strip or touching a private attribute.
        """
        return self._strip

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(len(self._scope_pixels[scope_key]))

    def update_pixels(
        self, scope_key: str, buffers: list[PixelBuffer], receipts: list[EffectReceipt]
    ) -> None:
        strip = self._strip
        seg = self._scope_pixels[scope_key]
        start = seg.start
        count = len(seg)

        if not buffers:
            for j in range(count):
                strip[start + j] = 0
            return

        pixels = buffers[-1]
        receipt = receipts[-1] if receipts else None
        brightness = receipt.brightness if receipt is not None else 1.0

        if brightness == 1.0:
            for j in range(count):
                strip[start + j] = pixels[j]
        else:
            for j in range(count):
                c = pixels[j]
                r = int(((c >> 16) & 0xFF) * brightness)
                g = int(((c >> 8) & 0xFF) * brightness)
                b = int((c & 0xFF) * brightness)
                strip[start + j] = (r << 16) | (g << 8) | b

    def clear_pixels(self, scope_key: str) -> None:
        strip = self._strip
        seg = self._scope_pixels[scope_key]
        start = seg.start
        for j in range(len(seg)):
            strip[start + j] = 0

    def flush(self) -> None:
        self._strip.show()
