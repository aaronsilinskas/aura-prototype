import audiobusio
import audiocore
import audiomixer
import board

from engine.effects.manager import EffectOutput
from engine.events import EffectEvent
from engine.packs import PackRegistry
from engine.state import EffectReceipt, Scope


class AudioEffectOutput(EffectOutput):
    """EffectOutput that plays WAV files via the PropMaker's built-in I2S amp.

    Registered on all scopes with ``receives_pixels = False`` — receives
    ``handle_event`` calls for every effect on every scope without incurring
    pixel buffer allocation.

    Uses a 2-voice ``audiomixer.Mixer``:
      - Voice 0 — ambient loop (``loop=True``); started when ``"ambient"`` is in
        ``scope_keys``.  Stopped when the matching receipt stops.
      - Voice 1 — one-shot; started for all other scopes.  Replaced immediately
        if a new one-shot starts.  Stopped automatically in ``flush()`` once
        playback ends naturally, or early if the receipt is stopped externally.
    """

    def __init__(self, registry: PackRegistry) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._registry = registry
        self._audio = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
        self._mixer = audiomixer.Mixer(
            voice_count=2,
            sample_rate=22050,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        self._audio.play(self._mixer)
        self._loop_file = None
        self._once_file = None
        self._loop_receipt: EffectReceipt | None = None
        self._once_receipt: EffectReceipt | None = None

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], receipt: EffectReceipt
    ) -> None:
        if event.verb == "start":
            path = self._registry.sound_path(event.pack, event.name)
            if path is None:
                return
            try:
                f = open(path, "rb")  # noqa: SIM115
            except OSError:
                return

            if "ambient" in scope_keys:
                # Voice 0 — looping ambient track
                self._mixer.voice[0].stop()
                if self._loop_file is not None:
                    self._loop_file.close()
                self._loop_file = f
                self._loop_receipt = receipt
                self._mixer.voice[0].play(audiocore.WaveFile(self._loop_file), loop=True)
            else:
                # Voice 1 — one-shot; replaces any current one-shot
                self._mixer.voice[1].stop()
                if self._once_file is not None:
                    self._once_file.close()
                self._once_file = f
                self._once_receipt = receipt
                self._mixer.voice[1].play(audiocore.WaveFile(self._once_file))

        elif event.verb == "stop":
            if receipt is self._loop_receipt:
                self._mixer.voice[0].stop()
                if self._loop_file is not None:
                    self._loop_file.close()
                    self._loop_file = None
                self._loop_receipt = None

    def flush(self) -> None:
        # Auto-stop one-shot when playback ends naturally
        if self._once_receipt is not None and not self._mixer.voice[1].playing:
            self._once_receipt.stop()
            if self._once_file is not None:
                self._once_file.close()
                self._once_file = None
            self._once_receipt = None

        # Stop voice 1 early if a rule stopped the receipt externally
        if self._once_receipt is not None and self._once_receipt.is_stopped():
            self._mixer.voice[1].stop()
            if self._once_file is not None:
                self._once_file.close()
                self._once_file = None
            self._once_receipt = None

        # Stop voice 0 if a rule stopped the loop receipt directly
        if self._loop_receipt is not None and self._loop_receipt.is_stopped():
            self._mixer.voice[0].stop()
            if self._loop_file is not None:
                self._loop_file.close()
                self._loop_file = None
            self._loop_receipt = None
