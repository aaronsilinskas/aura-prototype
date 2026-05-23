"""Interactive tuning display for SparkleStep across a pixel strip.

Each row shows one sparkle configuration running live, so you can compare how
parameter changes affect spawn density, brightness shape, and timing feel.

Columns explained:
  sparkle_count   — how many sparkles can be alive simultaneously
  spawn_delay     — seconds between sparkle respawns (random range)
  fade_in_rate    — intensity gained per second while fading in
  fade_out_rate   — intensity lost per second while fading out

Rows are defined in the CONFIGS list at the top of the file — edit freely to
explore the parameter space.

Run:
    uv run python examples/sparkle_tuning.py
"""

import sys
import time
from collections.abc import Iterable

from effects.effect import Effect, EffectState, EffectTimer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, PixelBuffer
from effects.steps.sparkle import sparkle
from effects.value import ValueGenerator as VG

PIXEL_COUNT = 36
FPS = 24

# fmt: off
# White sparkles on a dim indigo base.
SPARKLE_PALETTE = bytes([
      0,  10,  5, 20,   # dim indigo base
    128, 128, 64, 200,  # mid: soft violet-white
    255, 255, 255, 255, # peak: pure white
])
# fmt: on


def build_sparkle_renderer(
    sparkle_count: int,
    spawn_delay_min: float,
    spawn_delay_max: float,
    fade_in_rate: float,
    fade_out_rate: float,
) -> EffectRenderer:
    effect = Effect("sparkle", lambda _: 0.0).add_steps(
        [
            sparkle(
                sparkle_count=sparkle_count,
                spawn_delay_rate=VG.random(spawn_delay_min, spawn_delay_max),
                fade_in_rate=fade_in_rate,
                fade_out_rate=fade_out_rate,
            )
        ]
    )
    return EffectRenderer(effect, PaletteLUT256(SPARKLE_PALETTE))


# ---------------------------------------------------------------------------
# Configurations to compare — edit this list to explore the parameter space.
# Each entry: (label, sparkle_count, spawn_delay_min, spawn_delay_max, fade_in, fade_out)
# ---------------------------------------------------------------------------
CONFIGS = [
    ("sparse  slow", 2, 2.0, 4.0, 0.5, 0.5),
    ("sparse  fast", 2, 2.0, 4.0, 4.0, 4.0),
    ("medium  slow", 5, 1.0, 2.5, 0.5, 0.8),
    ("medium  fast", 5, 1.0, 2.5, 3.0, 3.0),
    ("dense   slow", 10, 0.3, 0.8, 0.4, 0.6),
    ("dense   fast", 10, 0.3, 0.8, 4.0, 2.0),
    ("burst   instant", 8, 0.1, 0.3, 100.0, 100.0),
    ("single  crawl", 1, 0.5, 1.0, 0.2, 0.2),
]
WARMUP_SECONDS = 2.0
LABEL_WIDTH = 16


def ansi_strip(colors: Iterable[int]) -> str:
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def main() -> None:
    renderers = []
    states = []
    for _label, sc, sdmin, sdmax, fi, fo in CONFIGS:
        renderers.append(build_sparkle_renderer(sc, sdmin, sdmax, fi, fo))
        states.append(EffectState())

    timer = EffectTimer()
    elapsed = 1.0 / FPS
    warmup_frames = int(WARMUP_SECONDS * FPS)
    row_count = len(CONFIGS)

    # Print static header once.
    header_label = " " * LABEL_WIDTH
    header_strip = "  " * PIXEL_COUNT  # width placeholder
    print(f"\033[1m{header_label}{'sparkle tuning':^{len(header_strip)}}\033[0m")
    print()
    for label, sc, sdmin, sdmax, fi, fo in CONFIGS:
        param = f"n={sc} delay={sdmin}-{sdmax}s in={fi} out={fo}"
        print(f"  {label:<{LABEL_WIDTH - 2}} {param}")
    print()

    # Reserve lines for the live strips.
    for _ in CONFIGS:
        print()
    # Move cursor back up to start of reserved block.
    sys.stdout.write(f"\033[{row_count}A")
    sys.stdout.flush()

    frame = 0
    try:
        while True:
            timer.update(elapsed)
            for renderer, state in zip(renderers, states):
                renderer.update(state, timer)

            if frame >= warmup_frames:
                for i, (renderer, state) in enumerate(zip(renderers, states)):
                    label = CONFIGS[i][0]
                    output = PixelBuffer(PIXEL_COUNT)
                    renderer.render(state, output)
                    sys.stdout.write(f"\r  {label:<{LABEL_WIDTH - 2}} {ansi_strip(output)}\n")
                # Move cursor back up for next frame.
                sys.stdout.write(f"\033[{row_count}A")
                sys.stdout.flush()

            frame += 1
            time.sleep(elapsed)

    except KeyboardInterrupt:
        # Move past the reserved block before exiting.
        sys.stdout.write(f"\033[{row_count}B\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
