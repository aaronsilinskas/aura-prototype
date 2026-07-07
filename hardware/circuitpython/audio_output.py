import audiobusio
import audiocore
import audiomixer

from effects.effect import Effect
from engine.audio import AudioRegistry
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt, Scope
from hardware.shared.voice_pool import VoicePool, VoiceSink


class AudioEffectOutput(EffectOutput, VoiceSink):
    """EffectOutput that plays WAV files via the PropMaker's built-in I2S amp.

    Registered on all scopes with ``receives_pixels = False`` — receives
    ``handle_event`` calls for every effect on every scope without incurring
    pixel buffer allocation.

    All voice-slot bookkeeping (slot occupancy, the eviction policy, the
    stops-receipt release rule, loudness tracking) lives in :class:`VoicePool`.
    This class is the live :class:`VoiceSink` adapter: it owns only hardware —
    the I2S amp, the ``audiomixer.Mixer``, the ``max_volume`` calibration, and a
    per-slot ``source`` list of open WAV files — and translates the pool's slot
    decisions into mixer and file-handle calls.  ``handle_event`` routes an
    effect's clip into ``pool.claim``; ``flush`` reconciles slots via
    ``pool.sweep``.
    """

    __slots__ = (
        "_audio",
        "_audio_registry",
        "_max_volume",
        "_mixer",
        "_pool",
        "_sources",
    )

    def __init__(
        self,
        audio_registry: AudioRegistry,
        max_volume: float,
        num_voices: int,
        *,
        i2s_bit_clock: object,
        i2s_word_select: object,
        i2s_data: object,
    ) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._audio_registry = audio_registry
        self._max_volume = max_volume
        self._pool = VoicePool(num_voices)
        self._audio = audiobusio.I2SOut(i2s_bit_clock, i2s_word_select, i2s_data)
        self._mixer = audiomixer.Mixer(
            voice_count=num_voices,
            sample_rate=11025,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        self._audio.play(self._mixer)

        # Per-slot opaque source: a (file, WaveFile) bundle while the slot plays,
        # or None when idle.  The file stays open until stop() closes it.
        self._sources: list[object | None] = [None] * num_voices

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        if effect.audio is None:
            return
        config = effect.audio.clips.get(event.verb)
        if config is None:
            return
        audio_only = effect.pixels is None and effect.vibration is None
        stops_receipt = audio_only or config.stops_effect
        path = self._audio_registry.path(config.name)
        if path is None:
            if stops_receipt:
                receipt.stop()
            return
        self._pool.claim(self, path, config.loop, stops_receipt, receipt)

    def flush(self) -> None:
        self._pool.sweep(self)

    # ------------------------------------------------------------------
    # VoiceSink — last-mile hardware mapping
    # ------------------------------------------------------------------

    def open_source(self, path: str) -> object | None:
        try:
            f = open(path, "rb")  # noqa: SIM115
        except OSError:
            return None
        return (f, audiocore.WaveFile(f))

    def play(self, slot: int, source: object, loop: bool) -> None:
        self._sources[slot] = source
        _, wave = source
        self._mixer.voice[slot].play(wave, loop=loop)

    def stop(self, slot: int) -> None:
        self._mixer.voice[slot].stop()
        source = self._sources[slot]
        if source is not None:
            f, _ = source
            f.close()
            self._sources[slot] = None

    def set_loudness(self, slot: int, loudness: float) -> None:
        self._mixer.voice[slot].level = self._max_volume * loudness

    def is_playing(self, slot: int) -> bool:
        return self._mixer.voice[slot].playing
