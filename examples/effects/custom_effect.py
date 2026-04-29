"""Build a custom effect from scratch using Shape, steps, and a palette.

Demonstrates the core building blocks for creating original effects:
  - Shape.checkers: a repeating pattern as the visual base
  - rotate: slides the pattern smoothly across the strip over time
  - drift_noise: overlays slowly-drifting per-pixel noise for organic shimmer
  - PaletteLUT256: a compact color stop definition expanded to a 256-entry LUT

On hardware, replace the animation loop with your LED write loop and call
render() per pixel to get packed RGB colors for neopixel or similar drivers.

Run:
    uv run python examples/custom_effect.py
"""

import sys
import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.shape import Shape
from effects.steps.drift_noise import drift_noise
from effects.steps.position import rotate

PIXEL_COUNT = 36
FPS = 30

# A custom palette mapping brightness [0.0, 1.0] to a violet-to-cyan gradient.
# Each entry is 4 bytes: [LUT_index (0–255), R, G, B].
# Intermediate positions are filled by linear interpolation at build time.
# fmt: off
COSMIC_PALETTE = bytes([
      0,   4,   0,  20,   # dark indigo base
     64,  24,   0, 120,   # muted violet
    160,  96,   0, 220,   # vivid purple-blue
    220,   0, 180, 255,   # bright cyan-magenta
    255,  80, 255, 255,   # near-white peak
])
# fmt: on


def ansi_strip(colors: list[int]) -> str:
    """Render a list of packed RGB colors as ANSI true-color terminal blocks."""
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def main() -> None:
    # --- Shape -------------------------------------------------------
    # Shape.checkers creates count repeating segments across the strip.
    # value=1.0 sets the flat zone to full brightness.
    # width=0.05 each checker is 5% of the width of the strip.
    shape = Shape.checkers(value=1.0, count=5, width=0.05)

    # --- Steps -------------------------------------------------------
    # Steps run once per frame in order, transforming position and/or value:
    #
    #   rotate: accumulates a position offset each frame so the entire checker
    #           pattern glides along the strip at 0.25 rotations per second.
    #
    #   drift_noise: maintains a small noise buffer that drifts over time.
    #                Each pixel samples the buffer, adding up to ±amplitude
    #                brightness variation — so neighbouring pixels shimmer
    #                independently rather than all changing together.
    #
    # The same Effect instance can drive many independent animations; all
    # mutable state is held in EffectState, not in the Effect or its steps.
    effect = Effect("cosmic_checkers", shape).add_steps(
        [
            rotate(rotations_per_second=0.25),
            drift_noise(resolution=PIXEL_COUNT, drift_speed=0.06, amplitude=0.3),
        ]
    )

    # --- Renderer ---------------------------------------------------
    # EffectRenderer ties an Effect to a Palette.
    # Call update() once per frame to advance step state.
    # Call render(state, position) per pixel to get a packed 0xRRGGBB color.
    palette = PaletteLUT256(COSMIC_PALETTE)
    renderer = EffectRenderer(effect, palette)

    # EffectState holds all mutable animation data for one running instance.
    # Create a fresh EffectState for each independent strip or animation.
    state = EffectState()
    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("Cosmic Checkers — press Ctrl+C to stop\n")

    try:
        while True:
            timer.update(elapsed)
            renderer.update(state, timer)

            colors = [renderer.render(state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)]
            sys.stdout.write(f"\r{ansi_strip(colors)}")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
