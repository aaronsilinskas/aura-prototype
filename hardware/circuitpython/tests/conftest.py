"""Stub out CircuitPython-only hardware modules so CPython can import audio_output."""

import sys
import types

for _name in ("audiobusio", "audiocore", "audiomixer", "board"):
    sys.modules.setdefault(_name, types.ModuleType(_name))

# board constants needed by AudioEffectOutput.__init__
_board = sys.modules["board"]
for _attr in ("I2S_BIT_CLOCK", "I2S_WORD_SELECT", "I2S_DATA"):
    if not hasattr(_board, _attr):
        setattr(_board, _attr, object())
