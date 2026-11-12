from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    EffectPixels,
    EffectVerb,
    HapticPattern,
    PixelBuffer,
)
from engine.effects.builder import EffectBuilder
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt


class SpyEffectOutput(EffectOutput):
    """Test spy that captures every ``update_pixels`` call for assertion."""

    def __init__(self, min_resolution: int, scopes: list, receives_pixels: bool = True) -> None:
        super().__init__(receives_pixels=receives_pixels)
        self.min_resolution = min_resolution
        self.scopes = scopes
        self.update_pixels_calls: list = []
        self.created_buffers: list = []
        self.create_buffer_key_calls: list = []
        self.handle_event_calls: list = []
        self.flush_calls: list = []
        self.clear_pixels_calls: list = []
        self.held_calls: list = []
        self.restored_calls: list = []

    def hold_effect(
        self, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        self.held_calls.append((scope_keys, effect, receipt))

    def restore_effect(
        self, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        self.restored_calls.append((scope_keys, effect, receipt))

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        self.handle_event_calls.append((event, scope_keys, effect, receipt))

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        buf = PixelBuffer(self.min_resolution)
        self.created_buffers.append(buf)
        self.create_buffer_key_calls.append(scope_key)
        return buf

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        self.update_pixels_calls.append((scope_key, buffer))

    def flush(self) -> None:
        self.flush_calls.append(True)

    def clear_pixels(self, scope_key: str) -> None:
        self.clear_pixels_calls.append(scope_key)


class _StubPixels(EffectPixels):
    """A no-op pixel renderer for testing."""

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: object) -> None:
        pass


class StubEffectBuilder(EffectBuilder):
    """Returns a minimal Effect with pixels for any effect name."""

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=_StubPixels())


class SpyEffect(EffectPixels):
    """Minimal EffectPixels that counts how many times ``update`` was called."""

    def __init__(self) -> None:
        self.update_count: int = 0

    def update(self, elapsed: float) -> None:
        self.update_count += 1

    def render(self, buf: object) -> None:
        pass


class SpyEffectBuilder(EffectBuilder):
    """Builder that records each SpyEffect it creates, for update-count assertions."""

    def __init__(self) -> None:
        self.created: list[SpyEffect] = []

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        effect = SpyEffect()
        self.created.append(effect)
        return Effect(name=name, pixels=effect)


class CapturingEffectBuilder(EffectBuilder):
    """Builder that captures the last ``EffectConfig`` it received."""

    def __init__(self) -> None:
        self.last_config: EffectConfig | None = None

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        self.last_config = config
        return Effect(name=name, pixels=_StubPixels())


class ColorFillEffectBuilder(EffectBuilder):
    """Builder whose effect renders a solid color into whatever buffer it is given.

    Fills every slot up to the buffer's current logical length, so it reflects
    a `MergeStrategy`'s ``prepare_buffers`` sizing (e.g. Split's per-effect
    partition) rather than the buffer's full allocated capacity.
    """

    def __init__(self, color: int) -> None:
        self._color = color

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        color = self._color

        class _ColorFillPixels(EffectPixels):
            def update(self, elapsed: float) -> None:
                pass

            def render(self, buf: PixelBuffer) -> None:
                for i in range(len(buf)):
                    buf[i] = color

        return Effect(name=name, pixels=_ColorFillPixels())


class UpdateCountFillEffectBuilder(EffectBuilder):
    """Builder whose effect fills its buffer with the number of updates it has had.

    A composed frame then shows how far the effect has advanced, so a test can
    tell an effect that froze from one that kept running.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        class _UpdateCountPixels(EffectPixels):
            def __init__(self) -> None:
                self.updates = 0

            def update(self, elapsed: float) -> None:
                self.updates += 1

            def render(self, buf: PixelBuffer) -> None:
                for i in range(len(buf)):
                    buf[i] = self.updates

        return Effect(name=name, pixels=_UpdateCountPixels())


class RenderLengthProbeEffectBuilder(EffectBuilder):
    """Builder whose effect records the buffer length seen at each ``render`` call.

    Used to confirm a `MergeStrategy`'s ``prepare_buffers`` sizing already
    happened by the time ``render`` runs.
    """

    def __init__(self) -> None:
        self.observed_lengths: list[int] = []

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        observed = self.observed_lengths

        class _ProbePixels(EffectPixels):
            def update(self, elapsed: float) -> None:
                pass

            def render(self, buf: PixelBuffer) -> None:
                observed.append(len(buf))

        return Effect(name=name, pixels=_ProbePixels())


class VerbFiringPixels(EffectPixels):
    """Test pixels that declare one custom verb, ``FIRED``, and emit it on every update.

    Built with ``fires=False`` they declare ``FIRED`` but never emit it.
    """

    FIRED = EffectVerb("fired")
    VERBS = (FIRED,)

    def __init__(self, config: EffectConfig, fires: bool = True) -> None:
        self._config = config
        self._fires = fires

    def update(self, elapsed: float) -> None:
        if self._fires:
            self._config.notify_listeners(self.FIRED)

    def render(self, output: object) -> None:
        pass


class AudioClipEffectBuilder(EffectBuilder):
    """Builder whose effects declare the given verb → clip-name map as audio.

    The ``AudioPlaybackConfig`` objects are made once, in ``clips``, and shared
    by every effect it builds, like a real effect's module-level constants.
    Its pixels are ``VerbFiringPixels``; when *fires* is set they emit
    ``VerbFiringPixels.FIRED`` on every update.
    """

    def __init__(self, clips: dict[EffectVerb, str], fires: bool = False) -> None:
        self.clips: dict[EffectVerb, AudioPlaybackConfig] = {
            verb: AudioPlaybackConfig(clip_name, loop=False) for verb, clip_name in clips.items()
        }
        self._fires = fires

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pixels = VerbFiringPixels(config, fires=self._fires)
        return Effect(name=name, pixels=pixels, audio=EffectAudio(self.clips))


class HapticPatternEffectBuilder(EffectBuilder):
    """Builder whose effects declare a one-click ``HapticPattern`` on each given verb.

    With *pixels* set, its pixels are non-firing ``VerbFiringPixels`` (declaring
    ``FIRED``); without, the effect has no pixels and so no custom verbs.
    """

    def __init__(self, verbs: list[EffectVerb], pixels: bool = True) -> None:
        self._patterns = {verb: HapticPattern([HapticPattern.SHARP_CLICK]) for verb in verbs}
        self._pixels = pixels

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        pixels = VerbFiringPixels(config, fires=False) if self._pixels else None
        return Effect(name=name, pixels=pixels, haptic=EffectHaptic(self._patterns))


class EventFiringEffectBuilder(EffectBuilder):
    """Builder whose effects emit ``VerbFiringPixels.FIRED`` on every update."""

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        return Effect(name=name, pixels=VerbFiringPixels(config))
