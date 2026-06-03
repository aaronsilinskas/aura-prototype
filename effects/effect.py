from __future__ import annotations

try:
    from collections.abc import Callable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

EffectListenerFunc: TypeAlias = "Callable[[str], None]"


class EffectPixels:
    """Abstract base class for pixel simulation and rendering.

    Owns the per-frame ``update``/``render`` contract that was previously on
    ``Effect``. Concrete subclasses: ``LayerRenderer``, ``AddColorsRenderer``,
    ``AddSamplesRenderer``, ``Solid``, ``PulseEffect``, ``LightningEffect``.
    ``EffectManager`` calls these methods directly on ``effect.pixels``; the
    ``Effect`` shell is not involved.
    """

    def update(self, elapsed: float) -> None:
        """Advance pixel state for the current frame."""
        raise NotImplementedError

    def render(self, output: PixelBuffer) -> None:
        """Write a packed RGB color for each pixel in ``output``."""
        raise NotImplementedError


class AudioPlaybackConfig:
    """Declares how a single audio clip should play.

    Fields:
      - ``name``: the clip name looked up in ``AudioRegistry``.
      - ``loop``: ``True`` → voice 0, looping background; ``False`` → voice 1, one-shot.
    """

    __slots__ = ["loop", "name"]

    def __init__(self, name: str, loop: bool) -> None:
        self.name = name
        self.loop = loop


class EffectAudio:
    """Capability object declaring the audio behaviour of an effect.

    ``clips`` maps event verbs to ``AudioPlaybackConfig`` instances.
    Set on ``Effect.audio``; if ``None``, the effect produces no audio.
    """

    __slots__ = ["clips"]

    def __init__(self, clips: dict) -> None:
        self.clips = clips


class EffectVibration:
    """Placeholder capability object for future vibration hardware support.

    ``patterns`` maps event verbs to opaque vibration config objects.
    Set on ``Effect.vibration``; no hardware output implements it yet.
    """

    __slots__ = ["patterns"]

    def __init__(self, patterns: dict) -> None:
        self.patterns = patterns


class EffectConfig:
    """Runtime configuration shared across a render pass.

    Passed to effect builders at construction. Controls the number of sample
    positions via ``resolution``. Registered listeners are called by name when
    significant rendering events occur.

    Constraints:
      - ``resolution`` is clamped to a minimum of ``1`` at construction.
    """

    __slots__ = ["listeners", "options", "resolution"]

    def __init__(
        self,
        resolution: int,
        options: dict | None = None,
        listeners: list[EffectListenerFunc] | None = None,
    ) -> None:
        self.resolution = max(1, resolution)
        self.options = options if options is not None else {}
        self.listeners = listeners if listeners is not None else []

    def notify_listeners(self, event_name: str) -> None:
        """Invoke all registered listeners with ``event_name``."""
        for listener in self.listeners:
            listener(event_name)


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

    def __iter__(self) -> Iterator[int]:
        return iter(self._pixels)


class Effect:
    """A descriptor declaring what capabilities an effect has.

    Constructor: ``Effect(name, pixels=None, audio=None, vibration=None)``.
    ``EffectManager`` inspects each capability field each tick:
      - ``pixels is None`` → no pixel buffer allocated, no render pass.
      - ``audio``/``vibration`` are passed to outputs via ``handle_event``.
    Builders return plain ``Effect`` instances — subclassing is only appropriate
    when there is genuine logic to add.
    """

    __slots__ = ["audio", "name", "pixels", "vibration"]

    def __init__(
        self,
        name: str,
        pixels: EffectPixels | None = None,
        audio: EffectAudio | None = None,
        vibration: EffectVibration | None = None,
    ) -> None:
        self.name = name
        self.pixels = pixels
        self.audio = audio
        self.vibration = vibration
