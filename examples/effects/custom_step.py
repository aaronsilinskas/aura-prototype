"""Demonstrate writing a custom EffectStep subclass.

EffectStep has three hook methods you can override:

  update(state, timer) -> bool
    Called once per frame. Do per-frame computation here and store any
    results in ``state`` via ``state.set_step_data(self, value)`` so that
    ``adjust_value`` (called per pixel) can read them cheaply without
    repeating the work. Each independent EffectState stores its own values,
    so one step instance safely drives many animations simultaneously.
    Return True to hand control to the next step (most modifiers always
    return True); return False to hold control this frame.

  adjust_position(state, position) -> float
    Called per pixel before the shape is sampled. Use it to translate,
    wrap, or otherwise warp the sampling position.

  adjust_value(state, position, value) -> float
    Called per pixel after the shape is sampled. Use it to scale, clamp,
    or otherwise modify the sampled brightness.

This example implements PulseStep — a modifier that multiplies the output
brightness by a slow sine wave, producing a gentle breathing pulse. The sine
oscillates between min_value and 1.0 at the given frequency (cycles/second).
The strip is displayed alongside a fixed-brightness version so the pulse is
easy to see.

Run:
    uv run python examples/custom_step.py
"""

import math
import sys
import time

from effects.effect import Effect, EffectState, EffectStep, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.shape import Shape
from effects.steps.position import rotate

PIXEL_COUNT = 36
FPS = 60

# fmt: off
ICE_PALETTE = bytes([
     0,   0,  64,   8,
    64,   0, 255,  32,
   128,   0, 255, 128,
   255, 255, 255, 255,
])
# fmt: on


class PulseStep(EffectStep):
    """Multiplies the output brightness by a sine wave at the given frequency.

    The sine oscillates between ``min_value`` and ``1.0``. ``frequency`` is in
    cycles per second.

    The multiplier is computed once per frame in ``update`` and stored in
    ``EffectState`` so ``adjust_value`` (called per pixel) only reads and
    applies it — avoiding a ``math.sin`` call on every pixel.
    """

    _TAU = 2.0 * math.pi

    def __init__(self, frequency: float, min_value: float = 0.1):
        self.frequency = frequency
        self.min_value = min_value
        self._multiplier_range = 1.0 - min_value

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        # Sine in [-1, 1]; remap to [min_value, 1.0] and store for adjust_value.
        sine = math.sin(self.frequency * timer.total * self._TAU)
        multiplier = self.min_value + self._multiplier_range * (sine / 2.0 + 0.5)
        state.set_step_data(self, multiplier)
        return True

    def adjust_value(self, state: EffectState, position: float, value: float) -> float:
        multiplier = state.get_step_data(self, float) or self.min_value
        return value * multiplier


def ansi_strip(colors: list[int]) -> str:
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def main() -> None:
    shape = Shape.gradient()
    palette = PaletteLUT256(ICE_PALETTE)

    # Steady — gradient + rotation, no pulse.
    steady_effect = Effect("steady", shape).add_steps([rotate(0.2)])
    steady_renderer = EffectRenderer(steady_effect, palette)
    steady_state = EffectState()

    # Pulsing — same gradient + rotation, plus PulseStep at 0.4 Hz.
    pulse_effect = Effect("pulsing", shape).add_steps(
        [
            rotate(0.2),
            PulseStep(frequency=0.4, min_value=0.05),
        ]
    )
    pulse_renderer = EffectRenderer(pulse_effect, palette)
    pulse_state = EffectState()

    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("Custom PulseStep example — press Ctrl+C to stop\n")
    print()
    print()

    try:
        while True:
            timer.update(elapsed)
            steady_renderer.update(steady_state, timer)
            pulse_renderer.update(pulse_state, timer)

            steady_colors = [
                steady_renderer.render(steady_state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]
            pulse_colors = [
                pulse_renderer.render(pulse_state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]

            sys.stdout.write("\033[2A")
            sys.stdout.write(f"\rSteady:  {ansi_strip(steady_colors)}\n")
            sys.stdout.write(f"\rPulsing: {ansi_strip(pulse_colors)}\n")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
