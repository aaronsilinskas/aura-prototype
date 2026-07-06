from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

from effects.effect import PixelBuffer
from engine.state import EffectReceipt

_FULL_BRIGHTNESS: Final = 1.0


def _brightness_of(receipt: EffectReceipt | None) -> float:
    """Return *receipt*'s brightness, or full brightness for a missing receipt."""
    return _FULL_BRIGHTNESS if receipt is None else receipt.brightness


def _scale_color(color: int, brightness: float) -> int:
    """Scale each RGB channel of *color* by *brightness*."""
    r = int(((color >> 16) & 255) * brightness)
    g = int(((color >> 8) & 255) * brightness)
    b = int((color & 255) * brightness)
    return (r << 16) | (g << 8) | b


class MergeStrategy:
    """Per-scope policy compositing a scope's layered effect buffers into one region buffer.

    This project's ``Protocol`` substitute: a plain base class whose methods
    only raise ``NotImplementedError``. Subclasses hold no per-instance state,
    so each ships as a module-level singleton (``SPLIT``, ``ADDITIVE``).
    """

    def prepare_buffers(self, buffers: list[PixelBuffer]) -> None:
        """Resize *buffers* to this strategy's layout ahead of the next ``merge`` call."""
        raise NotImplementedError

    def merge(
        self, buffers: list[PixelBuffer], receipts: list[EffectReceipt | None]
    ) -> PixelBuffer:
        """Composite *buffers* (each scaled by its parallel receipt's brightness) into buffers[0].

        Returns ``buffers[0]``, resized to the full region capacity.
        """
        raise NotImplementedError


class SplitMerge(MergeStrategy):
    """Divides the region into one contiguous, non-overlapping part per buffer."""

    def prepare_buffers(self, buffers: list[PixelBuffer]) -> None:
        """Size each buffer to its contiguous slice of the full region, bottom-to-top.

        The region divides evenly by ``len(buffers)`` where possible; the
        first ``region % len(buffers)`` parts each get one extra pixel.  When
        there are more buffers than pixels, the surplus buffers are sized to
        zero.
        """
        region = buffers[0].capacity
        base, remainder = divmod(region, len(buffers))
        for i, buf in enumerate(buffers):
            buf.resize(base + 1 if i < remainder else base)

    def merge(
        self, buffers: list[PixelBuffer], receipts: list[EffectReceipt | None]
    ) -> PixelBuffer:
        """Copy each buffer's (brightness-scaled) part into its slice of ``buffers[0]``."""
        dest = buffers[0]
        region = dest.capacity
        offset = 0
        for k in range(len(buffers)):
            buf = buffers[k]
            brightness = _brightness_of(receipts[k])
            part_len = len(buf)
            for i in range(part_len):
                dest[offset + i] = _scale_color(buf[i], brightness)
            offset += part_len
        dest.resize(region)
        return dest


class AdditiveMerge(MergeStrategy):
    """Composites all buffers over the full region by per-channel additive blend."""

    def prepare_buffers(self, buffers: list[PixelBuffer]) -> None:
        """Size every buffer to the full region width, even if previously sized differently."""
        region = buffers[0].capacity
        for buf in buffers:
            buf.resize(region)

    def merge(
        self, buffers: list[PixelBuffer], receipts: list[EffectReceipt | None]
    ) -> PixelBuffer:
        """Blend all (brightness-scaled) buffers per channel, clamped to 255, into buffers[0]."""
        dest = buffers[0]
        region = len(dest)
        dest_brightness = _brightness_of(receipts[0])
        for i in range(region):
            dest[i] = _scale_color(dest[i], dest_brightness)

        for k in range(1, len(buffers)):
            buf = buffers[k]
            brightness = _brightness_of(receipts[k])
            for i in range(region):
                c1 = dest[i]
                c2 = _scale_color(buf[i], brightness)
                r = min(255, ((c1 >> 16) & 255) + ((c2 >> 16) & 255))
                g = min(255, ((c1 >> 8) & 255) + ((c2 >> 8) & 255))
                b = min(255, (c1 & 255) + (c2 & 255))
                dest[i] = (r << 16) | (g << 8) | b
        return dest


SPLIT: Final = SplitMerge()
ADDITIVE: Final = AdditiveMerge()
