from __future__ import annotations

try:
    from collections.abc import Callable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

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
      - ``loop``: ``True`` → looping background; ``False`` → one-shot.
      - ``stops_effect``: ``False`` (default) → receipt lifecycle stays with rules;
        ``True`` → when this one-shot is released (natural finish or eviction) the
        owning ``EffectReceipt`` is stopped, ending the whole effect (pixels and
        haptic included).  Combining ``stops_effect=True`` with ``loop=True`` is
        a contradiction (a loop never finishes) and raises ``ValueError``.
    """

    __slots__ = ["loop", "name", "stops_effect"]

    def __init__(self, name: str, loop: bool, stops_effect: bool = False) -> None:
        if stops_effect and loop:
            raise ValueError(
                "stops_effect=True is incompatible with loop=True: a loop never finishes"
            )
        self.name = name
        self.loop = loop
        self.stops_effect = stops_effect


class EffectAudio:
    """Capability object declaring the audio behaviour of an effect.

    ``clips`` maps event verbs to ``AudioPlaybackConfig`` instances.
    Set on ``Effect.audio``; if ``None``, the effect produces no audio.
    """

    __slots__ = ["clips"]

    def __init__(self, clips: dict[str, AudioPlaybackConfig]) -> None:
        self.clips = clips


class HapticPattern:
    """Declares a haptic playback sequence as an ordered list of steps.

    Each step is one of the named class-level constants (effect or pause).
    Constants are deliberately offset from DRV2605L hardware waveform IDs
    (1, 4, 7, 10, 12, 14) so that passing a raw hardware ID to the output
    layer raises an error.  The mapping from these constants to actual
    DRV2605L waveform IDs lives inside ``Drv2605EffectOutput``.

    Effect constants:
      ``STRONG_CLICK``, ``SHARP_CLICK``, ``SOFT_BUMP``,
      ``DOUBLE_CLICK``, ``TRIPLE_CLICK``, ``STRONG_BUZZ``

    Pause constants:
      ``PAUSE_250``, ``PAUSE_500``, ``PAUSE_1000``
    """

    __slots__ = ["sequence"]

    # Effect constants — offset from DRV2605L IDs {1, 4, 7, 10, 12, 14}
    STRONG_CLICK: int = 101
    SHARP_CLICK: int = 104
    SOFT_BUMP: int = 107
    DOUBLE_CLICK: int = 110
    TRIPLE_CLICK: int = 112
    STRONG_BUZZ: int = 114

    # Pause constants — offset from DRV2605L IDs {1, 4, 7, 10, 12, 14}
    PAUSE_250: int = 201
    PAUSE_500: int = 202
    PAUSE_1000: int = 203

    def __init__(self, sequence: list[int]) -> None:
        self.sequence = sequence


class EffectHaptic:
    """Capability object declaring the haptic behaviour of an effect.

    ``patterns`` maps event verbs to ``HapticPattern`` instances.
    Set on ``Effect.haptic``; if ``None``, the effect produces no haptic output.
    """

    __slots__ = ["patterns"]

    def __init__(self, patterns: dict[str, HapticPattern]) -> None:
        self.patterns = patterns


class EffectConfig:
    """Runtime configuration shared across a render pass.

    Passed to effect builders at construction. Controls the number of sample
    positions via ``resolution``. Registered listeners are called by name when
    significant rendering events occur.

    Constraints:
      - ``resolution`` is clamped to a minimum of ``1`` at construction.
    """

    __slots__ = ["_options", "listeners", "resolution"]

    def __init__(
        self,
        resolution: int,
        options: dict[str, object] | None = None,
        listeners: list[EffectListenerFunc] | None = None,
    ) -> None:
        self.resolution = max(1, resolution)
        self._options = options if options is not None else {}
        self.listeners = listeners if listeners is not None else []

    def get_option(self, key: str, default: T) -> T:
        """Return the option stored at ``key``, or ``default`` if absent.

        The returned value is not coerced; it is assumed to match the type
        of ``default`` based on the caller's contract with the option.
        """
        if key in self._options:
            return self._options[key]  # type: ignore[return-value]
        return default

    def notify_listeners(self, event_name: str) -> None:
        """Invoke all registered listeners with ``event_name``."""
        for listener in self.listeners:
            listener(event_name)


class PixelBuffer:
    """In-memory pixel buffer backed by a list.

    Used in tests, examples, or any context where rendered colors are
    collected before being written to hardware.

    The backing list is allocated once at construction, at ``capacity`` size,
    and is never reallocated. ``resize`` only moves the logical length used
    by ``__len__`` within ``[0, capacity]`` — it does not touch the backing
    list. Indexing still addresses the full backing list regardless of the
    current logical length.
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

    @property
    def capacity(self) -> int:
        """Return the buffer's allocated size, independent of logical length."""
        return len(self._pixels)

    def resize(self, new_count: int) -> None:
        """Set the logical length reported by ``__len__`` to ``new_count``.

        ``new_count`` must be within ``[0, capacity]``; otherwise raises
        ``ValueError``. Does not reallocate the backing list.
        """
        if new_count < 0 or new_count > self.capacity:
            raise ValueError(f"new_count {new_count} out of range [0, {self.capacity}]")
        self._count = new_count


class Effect:
    """A descriptor declaring what capabilities an effect has.

    Constructor: ``Effect(name, pixels=None, audio=None, haptic=None)``.
    ``EffectManager`` inspects each capability field each tick:
      - ``pixels is None`` → no pixel buffer allocated, no render pass.
      - ``audio``/``haptic`` are passed to outputs via ``handle_event``.
    Builders return plain ``Effect`` instances — subclassing is only appropriate
    when there is genuine logic to add.
    """

    __slots__ = ["audio", "haptic", "name", "pixels"]

    def __init__(
        self,
        name: str,
        pixels: EffectPixels | None = None,
        audio: EffectAudio | None = None,
        haptic: EffectHaptic | None = None,
    ) -> None:
        self.name = name
        self.pixels = pixels
        self.audio = audio
        self.haptic = haptic
