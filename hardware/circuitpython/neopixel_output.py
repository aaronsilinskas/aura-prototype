"""NeoPixel-per-scope effect output — one strip per configured leaf scope.

The ``neopixel`` import lives only in ``device_builder`` (which supplies
already-initialised strip objects), keeping this module testable under CPython.
"""

from __future__ import annotations

from effects.effect import PixelBuffer
from engine.effects.manager import EffectOutput
from engine.state import ScopeValue

__all__ = ["NeoPixelEffectOutput"]


class NeoPixelEffectOutput(EffectOutput):
    """Routes one NeoPixel strip per configured leaf scope.

    Args:
        strips: Mapping of scope key → strip object supporting
            ``strip[i] = color`` (packed RGB int) and ``strip.show()``.
        counts: Mapping of scope key → pixel count for that strip.
        brightnesses: Mapping of scope key → per-scope brightness in
            [0.0, 1.0], applied on top of the per-effect receipt brightness.
    """

    __slots__ = ("_brightnesses", "_counts", "_strips", "_zero_bufs", "min_resolution", "scopes")

    def __init__(
        self,
        strips: dict[str, object],
        counts: dict[str, int],
        brightnesses: dict[str, float],
    ) -> None:
        super().__init__()
        self._strips: dict[str, object] = strips
        self._counts: dict[str, int] = counts
        self._brightnesses: dict[str, float] = brightnesses

        self._zero_bufs: dict[str, PixelBuffer] = {
            key: PixelBuffer(count) for key, count in counts.items()
        }

        self.scopes: list[ScopeValue] = [ScopeValue(key) for key in strips]
        self.min_resolution: int = max(counts.values()) if counts else 0

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(self._counts[scope_key])

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        strip = self._strips[scope_key]
        count = self._counts[scope_key]

        if not buffers:
            zero = self._zero_bufs[scope_key]
            for i in range(count):
                strip[i] = zero[i]
            return

        pixels = buffers[-1]
        receipt = receipts[-1] if receipts else None
        effect_brightness = receipt.brightness if receipt is not None else 1.0
        scope_brightness = self._brightnesses.get(scope_key, 1.0)
        brightness = effect_brightness * scope_brightness

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
        strip = self._strips[scope_key]
        count = self._counts[scope_key]
        for i in range(count):
            strip[i] = 0

    def flush(self) -> None:
        for strip in self._strips.values():
            strip.show()
