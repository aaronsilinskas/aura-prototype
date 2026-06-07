import audiobusio
import audiocore
import audiomixer
import board

from effects.effect import Effect
from engine.audio import AudioRegistry
from engine.effects.manager import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt, Scope


class AudioEffectOutput(EffectOutput):
    """EffectOutput that plays WAV files via the PropMaker's built-in I2S amp.

    Registered on all scopes with ``receives_pixels = False`` — receives
    ``handle_event`` calls for every effect on every scope without incurring
    pixel buffer allocation.

    Uses a 2-voice ``audiomixer.Mixer``:
      - Voice 0 — ambient loop (``loop=True``); started when
        ``effect.audio.clips[verb].loop`` is ``True``.  Stopped when the
        matching receipt stops (detected in ``flush()``).
      - Voice 1 — one-shot; started when ``loop`` is ``False``.  Replaced
        immediately if a new one-shot starts.  Stopped automatically in
        ``flush()`` once playback ends naturally, or early if the receipt is
        stopped externally.

    Teardown of both voices is driven entirely by ``flush()`` receipt guards.
    """

    def __init__(self, audio_registry: AudioRegistry, max_volume: float) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._audio_registry = audio_registry
        self._max_volume = max_volume
        self._audio = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
        self._mixer = audiomixer.Mixer(
            voice_count=2,
            sample_rate=11025,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )

        self._audio.play(self._mixer)
        self._loop_file = None
        self._loop_wave = None  # held to prevent GC collecting it during playback
        self._once_file = None
        self._once_wave = None  # held to prevent GC collecting it during playback
        self._loop_receipt: EffectReceipt | None = None
        self._once_receipt: EffectReceipt | None = None
        self._once_verb: str | None = None
        self._loop_loudness: float = 1.0
        self._once_loudness: float = 1.0

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        if effect.audio is None:
            return
        config = effect.audio.clips.get(event.verb)
        if config is None:
            return

        path = self._audio_registry.path(config.name)
        if path is None:
            return
        try:
            f = open(path, "rb")  # noqa: SIM115
        except OSError:
            return

        if config.loop:
            self._mixer.voice[0].stop()
            if self._loop_file is not None:
                self._loop_file.close()
            self._loop_wave = audiocore.WaveFile(f)
            self._loop_file = f
            self._loop_receipt = receipt
            self._loop_loudness = receipt.loudness
            self._mixer.voice[0].level = self._max_volume * receipt.loudness
            self._mixer.voice[0].play(self._loop_wave, loop=True)
        else:
            self._mixer.voice[1].stop()
            if self._once_file is not None:
                self._once_file.close()
            if self._once_receipt is not None and self._once_verb == "start":
                self._once_receipt.stop()
            self._once_file = f
            self._once_receipt = receipt
            self._once_verb = event.verb
            self._once_loudness = receipt.loudness
            self._mixer.voice[1].level = self._max_volume * receipt.loudness
            self._once_wave = audiocore.WaveFile(self._once_file)
            self._mixer.voice[1].play(self._once_wave)

    def flush(self) -> None:
        # Clean up one-shot state when playback ends naturally
        if self._once_receipt is not None and not self._mixer.voice[1].playing:
            if self._once_file is not None:
                self._once_file.close()
                self._once_file = None
            self._once_wave = None
            self._once_receipt = None
            self._once_verb = None
            self._once_loudness = 1.0

        # Stop voice 1 early if a rule stopped the receipt externally
        if self._once_receipt is not None and self._once_receipt.is_stopped():
            self._mixer.voice[1].stop()
            if self._once_file is not None:
                self._once_file.close()
                self._once_file = None
            self._once_wave = None
            self._once_receipt = None
            self._once_verb = None
            self._once_loudness = 1.0
        elif self._once_receipt is not None:
            loudness = self._once_receipt.loudness
            if loudness != self._once_loudness:
                self._mixer.voice[1].level = self._max_volume * loudness
                self._once_loudness = loudness

        # Stop voice 0 if a rule stopped the loop receipt directly
        if self._loop_receipt is not None and self._loop_receipt.is_stopped():
            self._mixer.voice[0].stop()
            if self._loop_file is not None:
                self._loop_file.close()
                self._loop_file = None
            self._loop_wave = None
            self._loop_receipt = None
            self._loop_loudness = 1.0
        elif self._loop_receipt is not None:
            loudness = self._loop_receipt.loudness
            if loudness != self._loop_loudness:
                self._mixer.voice[0].level = self._max_volume * loudness
                self._loop_loudness = loudness
