"""Demonstrate accelerate() and face_forward() for direction-aware animation.

Two strips run the same checker shape with a velocity that ramps from forward
(+0.5 rps) to reverse (−0.5 rps) and back in a repeating cycle:

  Without face_forward — the checkers slide back and forth, but the leading
    edge switches sides when direction reverses. The pattern looks like it
    bounces off walls.

  With face_forward — FaceForwardStep mirrors the sampling position whenever
    velocity is negative, so the bright leading edge always faces the direction
    of travel. The checkers appear to accelerate, decelerate, reverse, and
    accelerate again with a consistent "front."

The speed cycle is built with two duration() + accelerate() phases that
sequence automatically: when each duration expires it returns True and the
outer Effect advances to the next phase, looping back to phase A when both
are done.

Run:
    uv run python examples/direction_aware.py
"""

import sys
import time

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer
from effects.shape import Shape
from effects.steps.duration import duration
from effects.steps.position import accelerate, face_forward

PIXEL_COUNT = 36
FPS = 60

# fmt: off
COMET_PALETTE = bytes([
      0,   0,   0,   0,
     48,  20,   0,  80,
    128, 100,   0, 220,
    200, 220, 120, 255,
    255, 255, 255, 255,
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


def build_effect(with_face_forward: bool) -> Effect:
    # Checker pattern: 3 segments, 60% of each segment is lit.
    shape = Shape.checkers(value=1.0, count=3, width=0.05)

    # Two-phase speed cycle: each duration() runs its child accelerate() step
    # for 3 seconds then advances. The outer Effect wraps back to phase A when
    # phase B completes, producing a continuous forward→reverse→forward cycle.
    steps = [
        # Phase A: ramp from +0.5 rps down to −0.5 rps over 3 seconds.
        duration(
            3.0,
            persist_steps=False,
            steps=[
                accelerate(start=0.5, end=-0.5),
            ],
        ),
        # Phase B: ramp back from −0.5 rps up to +0.5 rps over 3 seconds.
        duration(
            3.0,
            persist_steps=False,
            steps=[
                accelerate(start=-0.5, end=0.5),
            ],
        ),
    ]

    if with_face_forward:
        # face_forward() must come after the velocity-writing step (accelerate)
        # so VelocitySharedData has been updated before the position mirror runs.
        # It is added outside duration() so it applies every frame regardless
        # of which phase is active.
        steps.append(face_forward())

    return Effect("direction_aware", shape).add_steps(steps)


def main() -> None:
    palette = PaletteLUT256(COMET_PALETTE)

    plain_renderer = EffectRenderer(build_effect(with_face_forward=False), palette)
    aware_renderer = EffectRenderer(build_effect(with_face_forward=True), palette)

    plain_state = EffectState()
    aware_state = EffectState()

    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("Direction-aware checkers — press Ctrl+C to stop\n")
    print()
    print()

    try:
        while True:
            timer.update(elapsed)
            plain_renderer.update(plain_state, timer)
            aware_renderer.update(aware_state, timer)

            plain_colors = [
                plain_renderer.render(plain_state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]
            aware_colors = [
                aware_renderer.render(aware_state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)
            ]

            sys.stdout.write("\033[2A")
            sys.stdout.write(f"\rWithout face_forward: {ansi_strip(plain_colors)}\n")
            sys.stdout.write(f"\rWith    face_forward: {ansi_strip(aware_colors)}\n")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
