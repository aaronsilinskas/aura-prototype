"""Demonstrate that one Effect instance drives many independent animations.

A single fire Effect is created once. Five separate EffectState objects are
created — one per strip — each evolving at its own pace. The Effect and its
steps hold no mutable data; all frame-to-frame state lives in EffectState.

On hardware this means you can define your element library once at startup and
share those objects across every strip, saving significant RAM.

Run:
    uv run python examples/multiple_states.py
"""

import sys
import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.steps.flame import flame

PIXEL_COUNT = 24
RESOLUTION = PIXEL_COUNT * 3
NUM_STRIPS = 5
FPS = 24

# fmt: off
fire_palette = bytes([
     0,  32,   0,   0,
    32, 128,   0,   0,
    92, 234,  35,   0,
   128, 255, 128,   0,
   192, 242,  85,   0,
   255, 216,   0,   0,
])
# fmt: on


def ansi_strip(colors: list[int]) -> str:
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def main() -> None:
    # One shared Effect — created once, never mutated after construction.
    fire_effect = Effect("fire").add_steps(
        [
            flame(
                spark_count=5, heat_rate=1.3, extra_cool_rate=0.1, resolution=RESOLUTION, spread=0.3
            ),
        ]
    )
    palette = PaletteLUT256(fire_palette)

    # One renderer wrapping the shared effect. render() is stateless beyond
    # reading from the EffectState passed in, so it's safe to share too.
    renderer = EffectRenderer(fire_effect, palette)

    # Independent EffectState per strip — this is the only per-strip cost.
    states = [EffectState() for _ in range(NUM_STRIPS)]
    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("Five independent fire animations — one Effect, five EffectStates\n")
    for _ in range(NUM_STRIPS):
        sys.stdout.write("\n")

    try:
        while True:
            timer.update(elapsed)

            # All strips share the renderer; each gets its own state.
            sys.stdout.write(f"\033[{NUM_STRIPS}A")
            for i, state in enumerate(states):
                renderer.update(state, timer)
                colors = [renderer.render(state, j / PIXEL_COUNT) for j in range(PIXEL_COUNT)]
                sys.stdout.write(f"\rStrip {i + 1}: {ansi_strip(colors)}\n")
            sys.stdout.flush()

            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
