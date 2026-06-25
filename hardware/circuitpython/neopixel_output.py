"""NeoPixel effect output — one strip per scope, one instance per scope.

The ``neopixel`` import lives only in ``device_builder`` (which supplies
already-initialised strip objects), keeping this module testable under CPython.
"""

from __future__ import annotations

from effects.effect import PixelBuffer
from engine.effects.manager import EffectOutput
from engine.state import ScopeValue

__all__ = ["NeoPixelEffectOutput"]


class NeoPixelEffectOutput(EffectOutput):
    """Routes a single NeoPixel strip for one configured leaf scope.

    Args:
        scope_key: The scope key this output serves.
        strip: Strip object supporting ``strip[i] = color`` (packed RGB int)
            and ``strip.show()``.
        count: Number of pixels on the strip.
        brightness: Per-scope brightness in [0.0, 1.0], applied on top of the
            per-effect receipt brightness.
    """

    __slots__ = ("_brightness", "_count", "_strip", "min_resolution", "scopes")

    def __init__(
        self,
        scope_key: str,
        strip: object,
        count: int,
        brightness: float = 1.0,
    ) -> None:
        super().__init__()
        self._strip = strip
        self._count: int = count
        self._brightness: float = brightness
        self.scopes: list[ScopeValue] = [ScopeValue(scope_key)]
        self.min_resolution: int = count

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(self._count)

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        strip = self._strip
        count = self._count

        if not buffers:
            for i in range(count):
                strip[i] = 0
            return

        pixels = buffers[-1]
        receipt = receipts[-1] if receipts else None
        effect_brightness = receipt.brightness if receipt is not None else 1.0
        brightness = effect_brightness * self._brightness

        if brightness == 1.0:
            for i in range(count):
                strip[i] = pixels[i]
        else:
            for i in range(count):
                c = pixels[i]
                r = int(((c >> 16) & 0xFF) * brightness)
                g = int(((c >> 8) & 0xFF) * brightness)
                b = int((c & 0xFF) * brightness)
                strip[i] = (r << 16) | (g << 8) | b

    def clear_pixels(self, scope_key: str) -> None:
        strip = self._strip
        for i in range(self._count):
            strip[i] = 0

    def flush(self) -> None:
        self._strip.show()
