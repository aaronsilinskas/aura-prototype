import audiobusio
import audiocore
import audiomixer
import board

from effects.render import PixelBuffer
from engine.effects.manager import EffectOutput
from engine.state import Scope


class AudioEffectOutput(EffectOutput):
    """EffectOutput that plays WAV files via the PropMaker's built-in I2S amp.

    On each effect event, opens ``sounds/<event_name>.wav`` and plays it
    non-blocking via ``audiobusio.I2SOut``.  If the file does not exist the
    event is silently ignored.  Only one sound plays at a time; a new event
    stops any in-progress playback before starting the new file.
    """

    def __init__(self) -> None:
        self.min_resolution = 1
        self.scopes = [Scope.PERSONAL]
        self._audio = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
        self._mixer = audiomixer.Mixer(
            voice_count=1,
            sample_rate=22050,
            channel_count=1,
            bits_per_sample=16,
            samples_signed=True,
        )
        self._mixer.voice[0].level = 0.01
        self._audio.play(self._mixer)
        self._wav_file = None

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(1)

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        pass

    def handle_event(self, event_name: str, scope_keys, receipt) -> None:
        if self._mixer.playing:
            return
        path = "sounds/" + event_name + ".wav"
        try:
            f = open(path, "rb")  # noqa: SIM115
        except OSError:
            return
        if self._wav_file is not None:
            self._wav_file.close()
        self._wav_file = f
        self._mixer.play(audiocore.WaveFile(self._wav_file))
