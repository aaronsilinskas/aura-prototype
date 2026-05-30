try:
    from collections.abc import Callable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

from effects.level import level_lerp as _level_lerp
from effects.level import level_lerp_int as _level_lerp_int

EffectListenerFunc: TypeAlias = "Callable[[str], None]"


class RendererConfig:
    """Runtime configuration shared across a render pass.

    Passed to effect builders at construction. Controls output intensity via
    ``level`` and the number of sample positions via ``resolution``.
    Registered listeners are called by name when significant rendering events
    occur.

    Constraints:
      - ``level`` is clamped to ``[1, 10]`` at construction.
      - ``resolution`` is clamped to a minimum of ``1`` at construction.
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

    def level_lerp(self, minimum: float, maximum: float) -> float:
        """Interpolate between ``minimum`` and ``maximum`` based on the current level."""
        return _level_lerp(self.level, minimum, maximum)

    def level_lerp_int(self, minimum: int, maximum: int) -> int:
        """Interpolate between ``minimum`` and ``maximum`` based on the current level,
        rounded to the nearest int."""
        return _level_lerp_int(self.level, minimum, maximum)


class PixelBuffer:
    """In-memory pixel buffer backed by a list.

    Used in tests, examples, or any context where rendered colors are
    collected before being written to hardware.
    """

    def __init__(self, count: int) -> None:
        self._pixels = [0] * count
        self._count = count

    def __setitem__(self, position: int, color: int) -> None:
        self._pixels[position] = color

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> int:
        return self._pixels[index]

    def __iter__(self) -> "Iterator[int]":
        return iter(self._pixels)


class EffectRenderer:
    """Base class for effect renderers.

    Update model:
      - Call ``update(elapsed)`` once per frame before ``render``.
    Rendering model:
      - Call ``render(output)`` once per frame to write packed RGB colors.
    Subclass contract:
      - Subclasses must implement ``name``, ``update``, and ``render``.
    """

    renders_pixels: bool = True
    """Whether this renderer produces pixel output.

    Non-pixel renderers (e.g. audio or event-only) set this to ``False`` to
    skip pixel buffer allocation for all outputs.
    """

    @property
    def name(self) -> str:
        """The name of this renderer."""
        raise NotImplementedError

    def update(self, elapsed: float) -> None:
        """Advance renderer state for the current frame."""
        raise NotImplementedError

    def render(self, output: PixelBuffer) -> None:
        """Write a packed RGB color for each pixel in ``output``."""
        raise NotImplementedError
