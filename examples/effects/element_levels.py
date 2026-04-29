"""Showcase all built-in element effects at a range of intensity levels.

Each element is displayed at levels 1, 4, 7, and 10 so you can see how the
intensity parameter shapes the animation. Each row shows one live-animated
second of that element at that level.

Run:
    uv run python examples/element_levels.py
    uv run python examples/element_levels.py fire          # one element
    uv run python examples/element_levels.py fire 7        # one element at one level
"""

import sys
import time

from effects.effect import EffectState, EffectTimer
from effects.elements.registry import ELEMENT_BUILDERS, build_element_renderer
from effects.render import RendererConfig

PIXEL_COUNT = 32
RESOLUTION = PIXEL_COUNT * 3
FPS = 24
WARMUP_SECONDS = 1.5  # advance silently so animations reach a representative state
SHOW_SECONDS = 2.0  # how long to display each level

SAMPLE_LEVELS = [1, 4, 7, 10]


def ansi_strip(colors: list[int]) -> str:
    """Render a list of packed RGB colors as ANSI true-color terminal blocks."""
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def show_element_level(name: str, level: int) -> None:
    """Animate one element at one level for SHOW_SECONDS, after a silent warmup."""
    config = RendererConfig(level=level, pixel_count=PIXEL_COUNT, resolution=RESOLUTION)
    state = EffectState()
    renderer = build_element_renderer(name, config)

    timer = EffectTimer()
    elapsed = 1.0 / FPS
    warmup_frames = int(WARMUP_SECONDS * FPS)
    show_frames = int(SHOW_SECONDS * FPS)
    label = f"  Level {level:2d}:  "

    for frame in range(warmup_frames + show_frames):
        timer.update(elapsed)
        renderer.update(state, timer)

        if frame >= warmup_frames:
            colors = [renderer.render(state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)]
            sys.stdout.write(f"\r{label}{ansi_strip(colors)}")
            sys.stdout.flush()
            time.sleep(elapsed)

    print()  # advance to next line


def show_element(name: str, levels: list[int]) -> None:
    print(f"\n\033[1m{name.upper()}\033[0m")
    for level in levels:
        show_element_level(name, level)


def main() -> None:
    element_arg = sys.argv[1] if len(sys.argv) > 1 else None
    level_arg = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if element_arg and level_arg:
        elements = [element_arg]
        levels = [level_arg]
    elif element_arg:
        elements = [element_arg]
        levels = SAMPLE_LEVELS
    else:
        elements = list(ELEMENT_BUILDERS.keys())
        levels = SAMPLE_LEVELS

    try:
        for name in elements:
            show_element(name, levels)
        print()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
