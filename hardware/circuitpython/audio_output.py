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

    Uses a flat pool of ``num_voices`` mixer voices.  Voice selection in
    ``handle_event`` iterates slots 0 to N-1 and claims the first whose
    receipt is ``None``.  If no idle slot exists the clip is silently dropped.

    ``flush()`` iterates all N slots each tick:
      1. Natural one-shot finish (``not voice[i].playing``) — frees the slot
         without stopping the receipt.
      2. Externally-stopped receipt — stops the voice and frees the slot.
      3. Loudness change — updates the voice level.
    """

    __slots__ = (
        "_audio",
        "_audio_registry",
        "_is_loop",
        "_loudness",
        "_max_volume",
        "_mixer",
        "_num_voices",
        "_receipts",
        "_wave_files",
        "_wave_objs",
    )

    def __init__(self, audio_registry: AudioRegistry, max_volume: float, num_voices: int) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._audio_registry = audio_registry
        self._max_volume = max_volume
        self._num_voices = num_voices
        self._audio = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
        self._mixer = audiomixer.Mixer(
            voice_count=num_voices,
            sample_rate=11025,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        self._audio.play(self._mixer)

        # Parallel lists — one entry per voice index, pre-allocated.
        # _wave_files holds raw file objects; _wave_objs holds audiocore.WaveFile instances.
        # Both are annotated as object because CircuitPython stubs for these types are
        # incomplete or unavailable at static-analysis time.
        self._receipts: list[EffectReceipt | None] = [None] * num_voices
        self._wave_files: list[object | None] = [None] * num_voices
        self._wave_objs: list[object | None] = [None] * num_voices
        self._loudness: list[float] = [1.0] * num_voices
        self._is_loop: list[bool] = [False] * num_voices

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

        # Claim first idle slot
        slot = -1
        for i in range(self._num_voices):
            if self._receipts[i] is None:
                slot = i
                break

        if slot == -1:
            # No idle slot — drop silently
            f.close()
            return

        self._mixer.voice[slot].stop()
        if self._wave_files[slot] is not None:
            self._wave_files[slot].close()

        self._wave_objs[slot] = audiocore.WaveFile(f)
        self._wave_files[slot] = f
        self._receipts[slot] = receipt
        self._loudness[slot] = receipt.loudness
        self._is_loop[slot] = config.loop
        self._mixer.voice[slot].level = self._max_volume * receipt.loudness
        self._mixer.voice[slot].play(self._wave_objs[slot], loop=config.loop)

    def flush(self) -> None:
        for i in range(self._num_voices):
            if self._receipts[i] is None:
                continue

            # 1. Natural one-shot finish — clear before stopped check
            if not self._is_loop[i] and not self._mixer.voice[i].playing:
                if self._wave_files[i] is not None:
                    self._wave_files[i].close()
                    self._wave_files[i] = None
                self._wave_objs[i] = None
                self._receipts[i] = None
                self._loudness[i] = 1.0
                self._is_loop[i] = False
                continue

            # 2. Externally-stopped receipt
            if self._receipts[i].is_stopped():
                self._mixer.voice[i].stop()
                if self._wave_files[i] is not None:
                    self._wave_files[i].close()
                    self._wave_files[i] = None
                self._wave_objs[i] = None
                self._receipts[i] = None
                self._loudness[i] = 1.0
                self._is_loop[i] = False
                continue

            # 3. Loudness update
            loudness = self._receipts[i].loudness
            if loudness != self._loudness[i]:
                self._mixer.voice[i].level = self._max_volume * loudness
                self._loudness[i] = loudness
