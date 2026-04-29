"""Demonstrate renderer types and RendererConfig event listeners.

Part 1 — Merge renderers (runs for 12 seconds):
  Displays three animations simultaneously so you can compare blend modes:

    Fire alone      — single EffectRenderer
    Average merge   — AverageMergeRenderer(fire, earth): averages RGB channels
    Additive merge  — AdditiveMergeRenderer(fire, earth): sums RGB channels, clamped

  Average merge is well-suited for mixing subtler layers: the combined brightness
  is the mean of both effects, so neither dominates the other.

  Additive merge is well-suited for layering light effects: bright pixels from
  either effect accumulate and white-hot spots appear where both are active.

Part 2 — Event listeners (runs until Ctrl+C):
  RendererConfig accepts a listeners list. The lightning element calls
  config.notify_listeners("lightning_strike") on each flash — useful for
  triggering sound effects, camera flashes, or haptic feedback in sync with
  the animation. Listeners receive the event name as a plain string.

Run:
    uv run python examples/using_renderers.py
"""

import sys
import time

from effects.effect import EffectState, EffectTimer
from effects.elements.earth import build_earth_renderer
from effects.elements.fire import build_fire_renderer
from effects.elements.lightning import build_lightning_renderer
from effects.render import AdditiveMergeRenderer, AverageMergeRenderer, RendererConfig

PIXEL_COUNT = 28
RESOLUTION = PIXEL_COUNT * 3
FPS = 24
LEVEL = 6
PART1_SECONDS = 12.0


def ansi_strip(colors: list[int]) -> str:
    """Render a list of packed RGB colors as ANSI true-color terminal blocks."""
    parts = []
    for color in colors:
        r = (color >> 16) & 0xFF
        g = (color >> 8) & 0xFF
        b = color & 0xFF
        parts.append(f"\033[48;2;{r};{g};{b}m  \033[0m")
    return "".join(parts)


def render_strip(renderer, state: EffectState) -> list[int]:
    return [renderer.render(state, i / PIXEL_COUNT) for i in range(PIXEL_COUNT)]


def part1_merge_comparison() -> None:
    """Show fire, fire+earth averaged, and fire+earth additive side by side."""
    config = RendererConfig(level=LEVEL, pixel_count=PIXEL_COUNT, resolution=RESOLUTION)

    # Build three independent renderer sets.
    # Each merge renderer owns its own child EffectRenderer instances — do not
    # share renderer objects across merge groups, as they share no state.
    fire_sole = build_fire_renderer(config)
    avg_renderer = AverageMergeRenderer([
        build_fire_renderer(config),
        build_earth_renderer(config),
    ])
    add_renderer = AdditiveMergeRenderer([
        build_fire_renderer(config),
        build_earth_renderer(config),
    ])

    # Each renderer needs its own EffectState.
    # State holds the mutable per-frame data (flame buffers, offsets, etc.)
    # for one running animation instance.
    state_fire = EffectState()
    state_avg = EffectState()
    state_add = EffectState()

    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print(f"\033[1mPart 1: Merge Renderers\033[0m (fire + earth at level {LEVEL})")
    print()
    # Reserve 3 lines for the animated strips.
    sys.stdout.write("Fire alone:      " + "  " * PIXEL_COUNT + "\n")
    sys.stdout.write("Average merge:   " + "  " * PIXEL_COUNT + "\n")
    sys.stdout.write("Additive merge:  " + "  " * PIXEL_COUNT + "\n")
    sys.stdout.flush()

    start = time.monotonic()
    while time.monotonic() - start < PART1_SECONDS:
        timer.update(elapsed)
        fire_sole.update(state_fire, timer)
        avg_renderer.update(state_avg, timer)
        add_renderer.update(state_add, timer)

        colors_fire = render_strip(fire_sole, state_fire)
        colors_avg = render_strip(avg_renderer, state_avg)
        colors_add = render_strip(add_renderer, state_add)

        # Move up 3 lines and overwrite each strip in place.
        sys.stdout.write("\033[3A")
        sys.stdout.write(f"\rFire alone:      {ansi_strip(colors_fire)}\n")
        sys.stdout.write(f"\rAverage merge:   {ansi_strip(colors_avg)}\n")
        sys.stdout.write(f"\rAdditive merge:  {ansi_strip(colors_add)}\n")
        sys.stdout.flush()
        time.sleep(elapsed)


def part2_event_listeners() -> None:
    """Show lightning with a RendererConfig event listener."""
    events: list[str] = []

    def on_event(event_name: str) -> None:
        # Collect events rather than printing directly so the terminal
        # output isn't disrupted by writes during renderer.update().
        events.append(event_name)

    # Attach the listener via RendererConfig. Any effect that calls
    # config.notify_listeners() will invoke all registered listeners.
    config = RendererConfig(
        level=8,
        pixel_count=PIXEL_COUNT,
        resolution=RESOLUTION,
        listeners=[on_event],
    )

    renderer = build_lightning_renderer(config)
    state = EffectState()
    timer = EffectTimer()
    elapsed = 1.0 / FPS

    print("\n\033[1mPart 2: Event Listeners\033[0m (lightning at level 8)")
    print("Each flash fires 'lightning_strike' — watch the counter rise.\n")
    # Reserve 2 lines for event display and the strip.
    sys.stdout.write("Last event:  (waiting...)                    \n")
    sys.stdout.write("Lightning:   " + "  " * PIXEL_COUNT + "\n")
    sys.stdout.flush()

    try:
        while True:
            timer.update(elapsed)
            renderer.update(state, timer)

            colors = render_strip(renderer, state)
            event_display = events[-1] if events else "(waiting...)"

            sys.stdout.write("\033[2A")
            sys.stdout.write(f"\rLast event:  {event_display} (total: {len(events):<4})\n")
            sys.stdout.write(f"\rLightning:   {ansi_strip(colors)}\n")
            sys.stdout.flush()
            time.sleep(elapsed)
    except KeyboardInterrupt:
        print("\nStopped.")


def main() -> None:
    try:
        part1_merge_comparison()
    except KeyboardInterrupt:
        print("\nStopped.")
        return

    part2_event_listeners()


if __name__ == "__main__":
    main()
