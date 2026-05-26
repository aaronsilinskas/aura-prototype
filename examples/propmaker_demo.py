"""CircuitPython hardware demo — RP2040 PropMaker + IS31FL3741 13×9 LED matrix.

A fire effect is hardcoded at startup and rendered across the LED matrix.
Subsequent issues add button input (#34), audio output (#35), and FPS
reporting (#36).

Hardware
--------
- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13×9 RGB LED Matrix Breakout (I2C on default SDA/SCL)

Installation
------------
1. Install CircuitPython on your PropMaker board:
   https://learn.adafruit.com/adafruit-feather-rp2040-prop-maker

2. Copy the following libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/

3. Copy the effects/ and engine/ directories to the CIRCUITPY drive root so
   they live at /CIRCUITPY/effects/ and /CIRCUITPY/engine/.

4. Copy this file to /CIRCUITPY/code.py.
   The board reboots and starts running automatically.

Configuration
-------------
- Buttons A–D on GP9–GP12 (pull-up) layer effects or clear all.
"""

import time

import adafruit_is31fl3741
import audiobusio
import audiocore
import audiomixer
import board
import busio
import digitalio
from adafruit_is31fl3741.adafruit_rgbmatrixqt import Adafruit_RGBMatrixQT

from effects.render import PixelBuffer
from engine.effects.manager import EffectManager, EffectOutput
from engine.engine import GameEngine, GameRule, Version
from engine.input import ButtonData, InputEvents, MovementData
from engine.packs import PackRegistry
from engine.state import SceneControls, Scope
from engine.timer import Timer

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def time_it(tag, fn, *args, **kwargs):
    start = time.monotonic()
    result = fn(*args, **kwargs)
    elapsed = time.monotonic() - start
    print(tag, fn.__name__, "took", elapsed, "s")
    return result


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MATRIX_COLS: "Final" = 13
_MATRIX_ROWS: "Final" = 9
_BUTTON_NAMES = ("A", "B", "C", "D")

BUTTON_A_PIN = board.D9
BUTTON_B_PIN = board.D10
BUTTON_C_PIN = board.D11
BUTTON_D_PIN = board.D12

# ---------------------------------------------------------------------------
# Hardware setup
# ---------------------------------------------------------------------------

i2c = busio.I2C(board.SCL, board.SDA)
while True:
    try:
        is31 = Adafruit_RGBMatrixQT(i2c, allocate=adafruit_is31fl3741.MUST_BUFFER)
        break
    except Exception:
        time.sleep(1)
is31.set_led_scaling(0x33)  # Brightness 0 -> 0xFF
is31.global_current = 0xFF  # limit LED current for safe testing; raise for full brightness
is31.enable = True

# Turn on power for audio amp
power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
power.switch_to_output(value=True)

# Button inputs with pull-up resistors (value=False when pressed)
_button_a = digitalio.DigitalInOut(BUTTON_A_PIN)
_button_a.switch_to_input(pull=digitalio.Pull.UP)
_button_b = digitalio.DigitalInOut(BUTTON_B_PIN)
_button_b.switch_to_input(pull=digitalio.Pull.UP)
_button_c = digitalio.DigitalInOut(BUTTON_C_PIN)
_button_c.switch_to_input(pull=digitalio.Pull.UP)
_button_d = digitalio.DigitalInOut(BUTTON_D_PIN)
_button_d.switch_to_input(pull=digitalio.Pull.UP)

# ---------------------------------------------------------------------------
# Effect system
# ---------------------------------------------------------------------------

_registry = PackRegistry(item_attr="BUILD")
_registry.scan_dir("packs/effects", "packs.effects")


class IS31FL3741EffectOutput(EffectOutput):
    """EffectOutput that drives the IS31FL3741 13×9 RGB LED matrix.

    Mapping: frame ``f`` → matrix row ``f``; pixel ``p`` → matrix column ``p``.
    Unused rows are cleared to black each tick. ``is31.show()`` is called once
    after all rows are written.
    """

    def __init__(self) -> None:
        self.min_resolution = _MATRIX_COLS
        self.scopes = [Scope.PERSONAL]

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        return PixelBuffer(_MATRIX_COLS)

    def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
        row_count = min(len(buffers), _MATRIX_ROWS)

        # Write active frames to their matrix rows
        for f in range(row_count):
            buf = buffers[f]
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, buf[p])  # pixel(x, y, packed_24bit_color)

        # Clear unused rows to black
        for f in range(row_count, _MATRIX_ROWS):
            for p in range(_MATRIX_COLS):
                is31.pixel(p, f, 0)

    def show_pixels(self) -> None:
        is31.show()


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

    def handle_event(self, event_name: str, scope, receipt) -> None:
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


class ButtonEffectRule(GameRule):
    def __init__(self):
        super().__init__("button_effects", Version(1, 0))

    def handle_event(self, event, state):
        if isinstance(event, InputEvents.ButtonAndMovement):
            button_data = event.buttons
            if button_data.states["A"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.fire", 5, {})
            elif button_data.states["B"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.water", 5, {})
            elif button_data.states["C"] == ButtonData.PRESSED:
                state.effect_controls.add_effect(Scope.PERSONAL, "elements.lightning", 2, {})
            elif button_data.states["D"] == ButtonData.PRESSED:
                state.effect_controls.stop_effect(Scope.ALL)


effect_output = IS31FL3741EffectOutput()
audio_output = AudioEffectOutput()
effect_manager = EffectManager(
    registry=_registry,
    outputs=[effect_output, audio_output],
)

game_engine = GameEngine(effect_controls=effect_manager)
game_engine.add_rules(ButtonEffectRule())
game_state = game_engine.create_state(SceneControls())

# Button state tracking for edge detection (pull-up: True = not pressed)
_buttons = [_button_a, _button_b, _button_c, _button_d]
_button_prev = [True, True, True, True]

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

timer = Timer()
_fps_frame_count = 0
_fps_window_start = time.monotonic()
while True:
    timer.update()
    effect_manager.update(timer)
    # time_it("effect_manager", effect_manager.update, timer)

    for _i, _btn in enumerate(_buttons):
        _current = _btn.value
        if not _current and _button_prev[_i]:  # falling edge: just pressed
            _states = dict.fromkeys(_BUTTON_NAMES, ButtonData.UP)
            _states[_BUTTON_NAMES[_i]] = ButtonData.PRESSED
            game_state.queue_event(
                InputEvents.ButtonAndMovement(ButtonData(_states), MovementData())
            )
        _button_prev[_i] = _current

    game_engine.update(game_state)
    # time_it("game_engine", game_engine.update, timer)

    _fps_frame_count += 1
    _fps_now = time.monotonic()
    if _fps_now - _fps_window_start >= 1.0:
        print("FPS:", _fps_frame_count)
        _fps_frame_count = 0
        _fps_window_start = _fps_now
