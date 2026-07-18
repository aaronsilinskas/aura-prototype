"""CircuitPython sound profiler -- drives the real `AudioEffectOutput` / `VoicePool` /
`VoiceSink` path to find the per-voice and mixer-fixed costs for the
`sound_component_costs` table in `docs/hardware/recorded-metrics.md` (see also
`docs/hardware/calibration-guide.md`).

Sweeps one axis:

- **concurrent voices** -- `CONCURRENT_VOICES`, the number of `handle_event` calls
  made (each claiming a `VoicePool` slot) before the steady-state loop begins, clamped
  to `NUM_VOICES` (`VoicePool`'s hard cap).

For each concurrent-voice count, the profiler:

1. Calls `AudioEffectOutput.handle_event` once per voice with a one-shot looping clip
   (each call claims one `VoicePool` slot via `pool.claim`).
2. Runs a steady-state loop calling `flush()` (which calls `VoicePool.sweep`) every
   frame, reporting `PerformanceTracker` stats -- this is the measured per-frame
   `cost_ms = mixer_fixed_ms + per_voice_ms * voices`.

`AudioEffectOutput` is registered on `Scope.ALL` -- there is exactly one shared sound
component per prop (one I2S amp + one `audiomixer.Mixer`), so this profiler drives it
directly rather than through `EffectManager`.

Hardware
--------
- An I2S amp (e.g. PropMaker FeatherWing) wired to `I2S_BIT_CLOCK_PIN_NAME`,
  `I2S_WORD_SELECT_PIN_NAME`, `I2S_DATA_PIN_NAME`.
- A short looping WAV file at `CLIP_PATH` on the board's filesystem (mono, 11025 Hz,
  16-bit, matching `AudioEffectOutput`'s mixer configuration).

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/sound_profiler.py
   The board reboots and starts running automatically.

Configuration
-------------
- NUM_VOICES: `VoicePool.num_voices` -- the hard cap on concurrent voices
- CONCURRENT_VOICES: voice counts to sweep, in order (each clamped to NUM_VOICES)
- CLIP_PATH: path to the looping WAV clip claimed by each voice
- MAX_VOLUME: `AudioEffectOutput`'s `max_volume` calibration
- TARGET_FPS: informational only -- included in the header for comparison against
  other profilers
- DISPLAY_SECONDS: how long to spend on each concurrent-voice count before advancing
- LOG_INTERVAL_SECONDS: how often the stats line is printed
- I2S_BIT_CLOCK_PIN_NAME / I2S_WORD_SELECT_PIN_NAME / I2S_DATA_PIN_NAME: board pin
  names for the I2S amp (defaults match Feather boards' `board.I2S_*` aliases)
"""

from __future__ import annotations

import time

import board

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio
from effects.performance import PerformanceTracker
from engine.audio import AudioRegistry
from engine.events import EffectEvent
from engine.state import EffectReceipt
from hardware.shared.profiler_report import (
    linear_fit,
    print_profile_header,
    print_stats_line,
    print_table_row,
)

try:
    from typing import Final
except ImportError:
    pass

NUM_VOICES: Final = 4
CONCURRENT_VOICES: Final = [1, 2, 4]
CLIP_PATH: Final = "sounds/sound_profiler.wav"
MAX_VOLUME: Final = 0.5
TARGET_FPS: Final = 24.0
DISPLAY_SECONDS: Final = 10.0
LOG_INTERVAL_SECONDS: Final = 5.0

# Boards without dedicated I2S_BIT_CLOCK/I2S_WORD_SELECT/I2S_DATA board-module
# aliases (e.g. non-Feather form factors) need real pin names here instead.
I2S_BIT_CLOCK_PIN_NAME: Final = "GP10"
I2S_WORD_SELECT_PIN_NAME: Final = "GP11"
I2S_DATA_PIN_NAME: Final = "GP12"

_CLIP_NAME: Final = "profiler_loop"
_EVENT_VERB: Final = "play"


def _build_output(audio_registry: AudioRegistry):
    from hardware.circuitpython.audio_output import AudioEffectOutput

    return AudioEffectOutput(
        audio_registry,
        max_volume=MAX_VOLUME,
        num_voices=NUM_VOICES,
        i2s_bit_clock=getattr(board, I2S_BIT_CLOCK_PIN_NAME),
        i2s_word_select=getattr(board, I2S_WORD_SELECT_PIN_NAME),
        i2s_data=getattr(board, I2S_DATA_PIN_NAME),
    )


def run() -> None:
    """Sweep concurrent voices, reporting per-frame mixer-fixed + per-voice cost."""
    audio_registry = AudioRegistry()
    audio_registry.register(_CLIP_NAME, CLIP_PATH)

    output = _build_output(audio_registry)

    looping_effect = Effect(
        "profiler.loop",
        audio=EffectAudio({_EVENT_VERB: AudioPlaybackConfig(_CLIP_NAME, loop=True)}),
    )
    play_event = EffectEvent("profiler", "loop", _EVENT_VERB)

    print_profile_header(
        component="sound",
        sweep_axes=["concurrent_voices", "num_voices"],
        sweep_values=[CONCURRENT_VOICES[0], NUM_VOICES],
        target_fps=TARGET_FPS,
    )

    # cost_ms = mixer_fixed_ms + per_voice_ms * effective_voices, so per-frame cost
    # is linear in the number of claimed voices: slope is per_voice_ms, intercept is
    # mixer_fixed_ms.
    voice_counts = []
    voice_update_ms = []
    for voices in CONCURRENT_VOICES:
        claimed = min(voices, NUM_VOICES)
        perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

        # Claim `claimed` voice slots -- each handle_event call plays the looping
        # clip on a new VoicePool slot via pool.claim.
        receipts = []
        for _ in range(claimed):
            receipt = EffectReceipt(0)
            output.handle_event(play_event, frozenset({"all"}), looping_effect, receipt)
            receipts.append(receipt)

        next_change_time = time.monotonic() + DISPLAY_SECONDS
        while True:
            perf.start_frame()
            perf.start_update_time()
            output.flush()
            perf.add_update_time()

            if perf.complete_frame():
                print_stats_line(
                    perf,
                    concurrent_voices=claimed,
                    num_voices=NUM_VOICES,
                )

            if perf.last_frame_end > next_change_time:
                break

        for receipt in receipts:
            receipt.stop()
        output.flush()

        voice_counts.append(claimed)
        voice_update_ms.append(perf.update_time_total / perf.frame_count * 1000.0)

    per_voice_ms, mixer_fixed_ms = linear_fit(voice_counts, voice_update_ms)
    print_table_row(
        "sound_component_costs",
        [f"{mixer_fixed_ms:.4f}", f"{per_voice_ms:.4f}"],
    )


run()
