try:
    from collections.abc import Callable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import Palette

EffectListenerFunc: TypeAlias = "Callable[[str], None]"


class RendererConfig:
    """Runtime configuration shared across a render pass.

    Holds the user-facing settings (level and resolution) that drive how an
    effect is sampled and scaled. Listeners are notified by name when
    significant events occur during rendering.
    """

    __slots__ = ["level", "listeners", "options", "resolution"]

    def __init__(
        self,
        level: int,
        resolution: int,
        options: dict | None = None,
        listeners: list[EffectListenerFunc] | None = None,
    ) -> None:
        self.level = min(max(1, level), 10)
        self.resolution = max(1, resolution)
        self.options = options if options is not None else {}
        self.listeners = listeners if listeners is not None else []

    def notify_listeners(self, event_name: str) -> None:
        """Invoke all registered listeners with ``event_name``."""
        for listener in self.listeners:
            listener(event_name)


class RendererOutput:
    def set_pixel(self, position: int, color: int) -> None:
        """Set the pixel at ``position`` to the given packed RGB color."""
        raise NotImplementedError

    @property
    def count(self) -> int:
        """Return the total number of pixels in this output."""
        raise NotImplementedError

    def __len__(self) -> int:
        return self.count


class PixelBuffer(RendererOutput):
    """In-memory pixel buffer backed by a list.

    Use wherever a concrete :class:`RendererOutput` is needed — in tests,
    examples, or any context where rendered colors are collected before
    being written to hardware.
    """

    def __init__(self, count: int) -> None:
        self._pixels = [0] * count
        self._count = count

    def set_pixel(self, position: int, color: int) -> None:
        self._pixels[position] = color

    @property
    def count(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> int:
        return self._pixels[index]

    def __iter__(self) -> "Iterator[int]":
        return iter(self._pixels)


class EffectRenderer:
    """Drives an effect through time and produces pixel colors for each position.

    This is the main object you advance each frame and sample per pixel to
    get the final colors for an LED strip.

    Contracts:
    - Call ``update`` once per frame to advance step state.
    - Call ``render`` per pixel to get a packed RGB int for a given position.
    """

    def __init__(self, effect: Effect, palette: Palette) -> None:
        self._effect = effect
        self._palette = palette

    @property
    def name(self) -> str:
        """The name of the underlying effect."""
        return self._effect.name

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        """Advance effect step state for the current frame."""
        self._effect.update(state, timer)

    def render(self, state: EffectState, output: RendererOutput) -> None:
        """Write a packed RGB color for each pixel in ``output``."""
        count = output.count
        for i in range(count):
            value = self._effect.value(state, i / count, count)
            color = self._palette.lookup(value)
            output.set_pixel(i, color)


class AverageMergeRenderer(EffectRenderer):
    """Combines multiple renderers by averaging their RGB channels per pixel."""

    def __init__(self, renderers: list[EffectRenderer]) -> None:
        self._renderers = renderers
        self._buffers: list[PixelBuffer] = []

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        for renderer in self._renderers:
            renderer.update(state, timer)

    def render(self, state: EffectState, output: RendererOutput) -> None:
        pixel_count = output.count
        if not self._buffers:
            self._buffers = [PixelBuffer(pixel_count) for _ in self._renderers]
        for renderer, buf in zip(self._renderers, self._buffers):
            renderer.render(state, buf)

        n = len(self._renderers)
        for i in range(pixel_count):
            r_total = 0
            g_total = 0
            b_total = 0
            for buf in self._buffers:
                color = buf[i]
                r_total += (color >> 16) & 255
                g_total += (color >> 8) & 255
                b_total += color & 255
            r = min(255, r_total // n)
            g = min(255, g_total // n)
            b = min(255, b_total // n)
            output.set_pixel(i, (r << 16) | (g << 8) | b)


class AdditiveMergeRenderer(EffectRenderer):
    """Combines multiple renderers by summing their RGB channels per pixel, clamped to ``255``."""

    def __init__(self, renderers: list[EffectRenderer]) -> None:
        self._renderers = renderers
        self._buffers: list[PixelBuffer] = []

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        for renderer in self._renderers:
            renderer.update(state, timer)

    def render(self, state: EffectState, output: RendererOutput) -> None:
        pixel_count = output.count
        if not self._buffers:
            self._buffers = [PixelBuffer(pixel_count) for _ in self._renderers]
        for renderer, buf in zip(self._renderers, self._buffers):
            renderer.render(state, buf)

        for i in range(pixel_count):
            r_total = 0
            g_total = 0
            b_total = 0
            for buf in self._buffers:
                color = buf[i]
                r_total += (color >> 16) & 255
                g_total += (color >> 8) & 255
                b_total += color & 255
            r = min(255, r_total)
            g = min(255, g_total)
            b = min(255, b_total)
            output.set_pixel(i, (r << 16) | (g << 8) | b)
