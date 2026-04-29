try:
    from collections.abc import Callable
    from typing import TypeAlias
except ImportError:
    pass

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import Palette

EffectListenerFunc: TypeAlias = "Callable[[str], None]"


class RendererConfig:
    """Runtime configuration shared across a render pass.

    Holds the user-facing settings (level, pixel count, resolution) that
    drive how an effect is sampled and scaled. Listeners are notified by
    name when significant events occur during rendering.
    """

    __slots__ = ["level", "listeners", "pixel_count", "resolution"]

    def __init__(
        self,
        level: int,
        pixel_count: int,
        resolution: int,
        listeners: list[EffectListenerFunc] | None = None,
    ):
        self.level = min(max(1, level), 10)
        self.pixel_count = max(1, pixel_count)
        self.resolution = max(1, resolution)
        self.listeners = listeners if listeners is not None else []

    def notify_listeners(self, event_name: str) -> None:
        """Invoke all registered listeners with ``event_name``."""
        for listener in self.listeners:
            listener(event_name)


class EffectRenderer:
    """Drives an effect through time and produces pixel colors for each position.

    This is the main object you advance each frame and sample per pixel to
    get the final colors for an LED strip.

    Contracts:
    - Call ``update`` once per frame to advance step state.
    - Call ``render`` per pixel to get a packed RGB int for a given position.
    """

    def __init__(self, effect: Effect, palette: Palette):
        self._effect = effect
        self._palette = palette

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        """Advance effect step state for the current frame."""
        self._effect.update(state, timer)

    def render(self, state: EffectState, position: float) -> int:
        """Return a packed RGB color for ``position`` based on the current effect state."""
        value = self._effect.value(state, position)
        color = self._palette.lookup(value)
        return color


class AverageMergeRenderer(EffectRenderer):
    """Combines multiple renderers by averaging their RGB channels per pixel."""

    def __init__(self, renderers: list[EffectRenderer]):
        self._renderers = renderers

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        for renderer in self._renderers:
            renderer.update(state, timer)

    def render(self, state: EffectState, position: float) -> int:
        r_total = 0
        g_total = 0
        b_total = 0
        for renderer in self._renderers:
            color = renderer.render(state, position)
            r = (color >> 16) & 255
            g = (color >> 8) & 255
            b = color & 255
            r_total += r
            g_total += g
            b_total += b

        count = len(self._renderers)
        r = min(255, r_total // count)
        g = min(255, g_total // count)
        b = min(255, b_total // count)
        return (r << 16) | (g << 8) | b


class AdditiveMergeRenderer(EffectRenderer):
    """Combines multiple renderers by summing their RGB channels per pixel, clamped to ``255``."""

    def __init__(self, renderers: list[EffectRenderer]):
        self._renderers = renderers

    def update(self, state: EffectState, timer: EffectTimer) -> None:
        for renderer in self._renderers:
            renderer.update(state, timer)

    def render(self, state: EffectState, position: float) -> int:
        r_total = 0
        g_total = 0
        b_total = 0
        for renderer in self._renderers:
            color = renderer.render(state, position)
            r = (color >> 16) & 255
            g = (color >> 8) & 255
            b = color & 255
            r_total += r
            g_total += g
            b_total += b

        r = min(255, r_total)
        g = min(255, g_total)
        b = min(255, b_total)
        return (r << 16) | (g << 8) | b
