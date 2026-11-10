from __future__ import annotations

try:
    from collections.abc import Callable, Iterable, Iterator
    from typing import TypeAlias
except ImportError:
    pass

try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

try:
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython


class EffectVerb:
    """A named moment an effect announces to its outputs; the key for ``clips`` and ``patterns``.

    The engine owns ``EffectVerb.START`` and ``EffectVerb.STOP``. Custom verbs
    are class constants on the ``EffectPixels`` subclass that emits them, listed
    in its ``VERBS``. ``name`` is for display only: two verbs with the same name
    are different verbs.
    """

    __slots__ = ["name"]

    # Not Final: a class cannot construct itself in its own body, so these are
    # assigned below it, and type checkers reject a Final declared without a value.
    START: EffectVerb
    STOP: EffectVerb

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"EffectVerb({self.name!r})"


EffectVerb.START = EffectVerb("start")
EffectVerb.STOP = EffectVerb("stop")

EffectListenerFunc: TypeAlias = "Callable[[EffectVerb], None]"


def _reject_non_verb_keys(field: str, keys: Iterable[object]) -> None:
    for key in keys:
        if not isinstance(key, EffectVerb):
            raise TypeError(
                f"{field} key {key!r} is not an EffectVerb: key by EffectVerb.START "
                + "or EffectVerb.STOP, or by the emitting effect's constant "
                + "(PulseEffect.PEAK)"
            )


class EffectPixels:
    """The sight **Modality**: abstract base for pixel simulation and rendering.

    ``EffectManager`` drives the per-frame ``update``/``render`` contract
    directly on ``effect.pixels``; the ``Effect`` shell is not involved.

    ``VERBS`` lists the custom verbs (**EffectVerb**) a subclass emits through
    ``EffectConfig.notify_listeners``, each also defined as a class constant
    (``PulseEffect.PEAK``). Empty by default: such an effect emits only
    ``EffectVerb.START`` and ``EffectVerb.STOP``, which the engine sends.
    Custom verbs are emitted from ``update``, never while the builder runs:
    ``EffectManager`` has no effect to hand its outputs until the builder returns.
    """

    VERBS: tuple[EffectVerb, ...] = ()

    def update(self, elapsed: float) -> None:
        """Advance pixel state for the current frame."""
        raise NotImplementedError

    def render(self, output: PixelBuffer) -> None:
        """Write a packed RGB color for each pixel in ``output``."""
        raise NotImplementedError


class AudioPlaybackConfig:
    """Declares how a single audio clip should play.

    Fields:
      - ``name``: the qualified clip name, resolved when the effect is built.
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


class ResolvedClip:
    """A declared ``AudioPlaybackConfig`` paired with the WAV path its name resolved to.

    Made by ``EffectManager`` when an effect is built and carried on that
    verb's ``EffectEvent``. ``config`` is the declared object itself, shared
    with every effect built from the same declaration, so it is never modified.
    """

    __slots__ = ["config", "path"]

    def __init__(self, config: AudioPlaybackConfig, path: str) -> None:
        self.config = config
        self.path = path


class EffectAudio:
    """The sound **Modality**: declares the audio behaviour of an effect.

    ``clips`` maps each **EffectVerb** to an ``AudioPlaybackConfig``; a key
    that is not an ``EffectVerb`` raises ``TypeError``.
    Set on ``Effect.audio``; if ``None``, the effect produces no audio.
    """

    __slots__ = ["clips"]

    def __init__(self, clips: dict[EffectVerb, AudioPlaybackConfig]) -> None:
        _reject_non_verb_keys("clips", clips)
        self.clips = clips


class HapticPattern:
    """Declares a haptic playback sequence as an ordered list of steps.

    Each step is one of the named class-level constants (an effect or a pause).
    The constants are deliberately kept clear of the DRV2605L hardware waveform
    IDs (1, 4, 7, 10, 12, 14) so that passing a raw hardware ID to the output
    layer raises an error. ``Drv2605EffectOutput`` maps these constants to the
    actual DRV2605L waveform IDs.
    """

    __slots__ = ["sequence"]

    STRONG_CLICK: Final = 101
    SHARP_CLICK: Final = 104
    SOFT_BUMP: Final = 107
    DOUBLE_CLICK: Final = 110
    TRIPLE_CLICK: Final = 112
    STRONG_BUZZ: Final = 114

    PAUSE_250: Final = 201
    PAUSE_500: Final = 202
    PAUSE_1000: Final = 203

    def __init__(self, sequence: list[int]) -> None:
        self.sequence = sequence


class EffectHaptic:
    """The touch **Modality**: declares the haptic behaviour of an effect.

    ``patterns`` maps each **EffectVerb** to a ``HapticPattern``; a key that
    is not an ``EffectVerb`` raises ``TypeError``.
    Set on ``Effect.haptic``; if ``None``, the effect produces no haptic output.
    """

    __slots__ = ["patterns"]

    def __init__(self, patterns: dict[EffectVerb, HapticPattern]) -> None:
        _reject_non_verb_keys("patterns", patterns)
        self.patterns = patterns


class EffectConfig:
    """Runtime configuration shared across a render pass.

    Passed to effect builders at construction. Controls the number of sample
    positions via ``resolution``. Registered listeners hear each **EffectVerb**
    the effect announces through ``notify_listeners``.

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
            return self._options[key]  # type: ignore[return-value]  # typed like default by contract
        return default

    def notify_listeners(self, verb: EffectVerb) -> None:
        """Announce ``verb`` to every registered listener, in registration order."""
        for listener in self.listeners:
            listener(verb)


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
    """A descriptor declaring which modalities (sight, sound, touch) an effect has.

    ``EffectManager`` inspects each modality field each tick:
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

    def emitted_verbs(self) -> tuple[EffectVerb, ...]:
        """Return every verb this effect can emit, the keys its ``clips`` and ``patterns`` may use.

        That is ``EffectVerb.START``, ``EffectVerb.STOP`` and the custom verbs
        its pixels declare in ``VERBS``. Builds a new tuple on each call, so
        ``EffectManager`` calls it once when the effect is built, never per tick.
        """
        if self.pixels is None:
            return (EffectVerb.START, EffectVerb.STOP)
        return (EffectVerb.START, EffectVerb.STOP) + self.pixels.VERBS
