"""Demonstrate step sequencing using hide, call, duration, and multiplier.

Builds a repeating "spell strike" effect that cycles through four phases:

  Phase 1  hide(random 0.5–2s)
             Blanks all output while waiting for the next strike.

  Phase 2  call(on_strike)
             Fires a callback at the exact moment of the strike.
             call() returns True immediately — no visual change, zero delay.
             Use it to trigger sound cues, haptics, logging, etc.

  Phase 3  duration(0.15s) + multiplier(0.0 → 1.0)
             Ramps from dark to full brightness in 0.15 seconds.

  Phase 4  duration(0.6s) + multiplier(1.0 → 0.0)
             Dims back to dark over 0.6 seconds, then loops to Phase 1.

Key concepts:
  - Steps form a sequence that advances automatically: a step returning True
    from update() hands control to the next step, wrapping back to step 0.
  - multiplier() reads timer.progress to know the interpolation position.
    It must live inside a duration() step that supplies a timed progress value.
  - duration() isolates child steps with their own EffectTimer so the outer
    timer's progress doesn't interfere.

Run:
    uv run python examples/step_sequencing.py
"""

import sys
import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.shape import Shape
from effects.steps.control import call, hide
from effects.steps.duration import duration
from effects.steps.scale import multiplier
from effects.value import ValueGenerator as VG

PIXEL_COUNT = 36
FPS = 60

# Bright gold-to-white palette for a spell-flash feel.
# fmt: off
STRIKE_PALETTE = bytes([
      0,   0,   0,   0,   # black (idle)
     64,  80,  20,   0,   # dark orange-red
    128, 220, 100,   0,   # bright amber
    200, 255, 220,  60,   # yellow-white
    255, 255, 255, 240,   # near-white peak
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
    strike_count = 0

    # call() delivers the current EffectState and EffectTimer at the moment
    # of activation, so callbacks can read or mutate shared animation state.
    def on_strike(state: EffectState, timer: EffectTimer) -> None:
        nonlocal strike_count
        strike_count += 1

    # Shape: a centered glow with 25% padding on each side.
    # padded() adds dead-zones so the glow hovers in the center of the strip.
    shape = Shape.padded(0.25, Shape.centered_gradient())

    effect = Effect("spell_strike", shape).add_steps([
        # Phase 1: blank output for a random 0.5–2.0s pause.
        hide(duration=VG.random(0.5, 2.0)),

        # Phase 2: trigger the strike callback with no visual delay.
        call(on_strike),

        # Phase 3: flash from dark to full brightness over 0.15 seconds.
        # multiplier() interpolates from start to end using timer.progress,
        # so it must be wrapped in a duration() that supplies timed progress.
        duration(0.15, steps=[multiplier(0.0, 1.0)]),

        # Phase 4: fade back to dark over 0.6 seconds.
        duration(0.60, steps=[multiplier(1.0, 0.0)]),
    ])

    renderer = EffectRenderer(effect, PaletteLUT256(STRIKE_PALETTE))
    state = EffectState()
    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("Spell Strike — press Ctrl+C to stop\n")
    # Reserve 2 lines: status and the strip.
    print()
    print()

    try:
        while True:
            timer.update(elapsed)
            renderer.update(state, timer)

            colors = [renderer.render(state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)]
            sys.stdout.write("\033[2A")
            sys.stdout.write(f"\rStrikes: {strike_count:<4}  elapsed: {timer.total:6.1f}s\n")
            sys.stdout.write(f"\r{ansi_strip(colors)}\n")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
