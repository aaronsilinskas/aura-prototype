try:
    from collections.abc import Callable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

from effects.level import level_lerp as _level_lerp
from effects.level import level_lerp_int as _level_lerp_int

EffectListenerFunc: TypeAlias = "Callable[[str], None]"


class EffectTimer:
    """Tracks frame timing for effect renderers.

    ``elapsed`` is the last frame delta, ``total`` is cumulative elapsed time,
    and ``progress`` is normalized to ``[0.0, 1.0]`` when a finite duration is
    set. When ``duration`` is ``None``, ``progress`` stays ``0.0`` and
    ``update`` always returns ``False``.
    """

    __slots__ = ("duration", "elapsed", "progress", "total")

    def __init__(self, duration: float | None = None):
        self.elapsed: float = 0.0
        self.total: float = 0.0
        self.duration: float | None = duration
        self.progress: float = 0.0

    def update(self, elapsed: float) -> bool:
        """Advance timer by one frame delta and return whether duration is complete."""
        self.elapsed = elapsed
        self.total += elapsed
        if self.duration is not None and self.duration > 0:
            self.progress = min(1.0, self.total / self.duration)

        return self.progress >= 1.0

    def __str__(self) -> str:
        return (
            f"EffectTimer(elapsed={self.elapsed}, total={self.total}, "
            f"duration={self.duration}, progress={self.progress})"
        )


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

    Subclasses must implement ``name``, ``update``, and ``render``.
    """

    @property
    def name(self) -> str:
        """The name of this renderer."""
        raise NotImplementedError

    def update(self, timer: EffectTimer) -> None:
        """Advance renderer state for the current frame."""
        raise NotImplementedError

    def render(self, output: "PixelBuffer") -> None:
        """Write a packed RGB color for each pixel in ``output``."""
        raise NotImplementedError
