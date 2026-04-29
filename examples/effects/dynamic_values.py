"""Demonstrate DynamicValue: fixed floats vs. VG.random() and VG.random_choice().

A DynamicValue is either a plain float or a zero-argument callable returning
a float. Steps call ValueGenerator.resolve() to evaluate either form, so the
same parameter slot accepts a literal or a generator without branching.

Random values are sampled once when the step initializes its state, not on
every frame. This means each EffectState initialization draws a fresh random
value, producing a visually distinct animation — even though the Effect and
steps are shared objects.

This example builds three fire animations from the same Effect:
  Fixed     — fixed spark_count and heat_rate; identical initial state.
  Random A  — VG.random() parameters; random values drawn at state init.
  Random B  — same factory as Random A; different values drawn independently.

Watch how Random A and Random B diverge despite being configured identically.

Run:
    uv run python examples/dynamic_values.py
"""

import sys
import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.steps.flame import flame
from effects.value import ValueGenerator as VG

PIXEL_COUNT = 28
RESOLUTION = PIXEL_COUNT * 3
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
    palette = PaletteLUT256(fire_palette)

    # Fixed parameters — every EffectState initialized from this effect
    # starts with identical spark behavior.
    fixed_effect = Effect("fire_fixed").add_steps(
        [
            flame(
                spark_count=5,
                heat_rate=1.3,
                extra_cool_rate=0.1,
                resolution=RESOLUTION,
                spread=0.3,
            ),
        ]
    )

    # Dynamic parameters — VG.random() returns a callable that produces a new
    # random float each time it is called. Steps call it once when they
    # initialize their internal state (on first update), so each EffectState
    # draws its own independent values.
    random_effect = Effect("fire_random").add_steps(
        [
            flame(
                spark_count=VG.random(3, 8),
                heat_rate=VG.random(1.0, 1.6),
                extra_cool_rate=VG.random(0.05, 0.2),
                resolution=RESOLUTION,
                spread=0.3,
            ),
        ]
    )

    fixed_renderer = EffectRenderer(fixed_effect, palette)
    # Both random strips share the same random_effect/renderer — but each
    # EffectState will sample the DynamicValue callables independently.
    random_renderer = EffectRenderer(random_effect, palette)

    fixed_state = EffectState()
    random_state_a = EffectState()
    random_state_b = EffectState()

    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("DynamicValue: fixed vs random parameters — press Ctrl+C to stop\n")
    print()
    print()
    print()

    try:
        while True:
            timer.update(elapsed)
            fixed_renderer.update(fixed_state, timer)
            random_renderer.update(random_state_a, timer)
            random_renderer.update(random_state_b, timer)

            fixed_colors = [
                fixed_renderer.render(fixed_state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]
            colors_a = [
                random_renderer.render(random_state_a, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]
            colors_b = [
                random_renderer.render(random_state_b, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]

            sys.stdout.write("\033[3A")
            sys.stdout.write(f"\rFixed:    {ansi_strip(fixed_colors)}\n")
            sys.stdout.write(f"\rRandom A: {ansi_strip(colors_a)}\n")
            sys.stdout.write(f"\rRandom B: {ansi_strip(colors_b)}\n")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
