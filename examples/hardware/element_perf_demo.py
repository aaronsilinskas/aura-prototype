"""CircuitPython element performance demo — all element effects cycling through intensity levels.

Each element is displayed at levels 1, 4, 7, and 10 in sequence, spending
DISPLAY_SECONDS on each before advancing to the next level, then the next
element. Performance stats are printed to the serial console every 5 seconds.

Hardware
--------
- A CircuitPython-compatible board (tested on Adafruit RP2040 boards)
- A NeoPixel LED ring or strip connected to pin D5 (change NUM_LEDS and the
  pin constant below to match your wiring)

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Install required libraries onto the CIRCUITPY drive (lib/ folder).
   Download the Adafruit CircuitPython Library Bundle for your CircuitPython
   version from https://circuitpython.org/libraries, then copy:
     - neopixel.mpy
     - adafruit_pixelbuf.mpy

3. Copy the entire effects/ directory from this repo onto the CIRCUITPY drive
   so it lives at /CIRCUITPY/effects/.

4. Copy this file to the root of the CIRCUITPY drive as code.py:
     cp examples/hardware/element_perf_demo.py /Volumes/CIRCUITPY/code.py

5. The board will reboot and start running automatically.

Configuration
-------------
- NUM_LEDS: number of LEDs in your strip or ring
- PIXELS_PIN: the board pin your data line is connected to (default: board.D5)
- SAMPLE_LEVELS: which intensity levels to cycle through
- DISPLAY_SECONDS: how long to show each element/level combination
"""

import gc
import time

import board
import neopixel

from effects.effect import EffectConfig, PixelBuffer
from effects.performance import PerformanceTracker
from engine.effects.manager import EffectBuilder
from engine.packs import PackRegistry

NUM_LEDS = 12
PIXELS_PIN = board.D5

# Adafruit PropMaker RP2040 external power RGB strip
# power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
# power.switch_to_output(value=True)
# PIXELS_PIN=board.EXTERNAL_NEOPIXELS

pixels = neopixel.NeoPixel(pin=PIXELS_PIN, n=NUM_LEDS, brightness=0.5, auto_write=False)

SAMPLE_LEVELS = [1, 4, 7, 10]
DISPLAY_SECONDS = 10.0

_registry = PackRegistry(item_attr="BUILD")
_registry.scan_dir("packs/effects", "packs.effects")

last_update = time.monotonic()


def logging_listener(event_name: str) -> None:
    print(f"Event: {event_name}")


def create_effect(element: str, level: int):
    config = EffectConfig(
        resolution=NUM_LEDS * 3,
        options={"level": level},
        listeners=[logging_listener],
    )
    builder = _registry.get("elements", element, EffectBuilder)
    return builder("elements." + element, config)


element_names = _registry.items("elements")
element_index = 0
level_index = 0
current_element = element_names[element_index]
current_level = SAMPLE_LEVELS[level_index]
current_effect = create_effect(current_element, current_level)

print("Available elements:", ", ".join(element_names))
print(f"Element: {current_element}, Level: {current_level}")

perf = PerformanceTracker(log_interval=5.0)
next_change_time = time.monotonic() + DISPLAY_SECONDS

while True:
    current_time = time.monotonic()
    elapsed_time = current_time - last_update
    last_update = current_time

    perf.start_frame()

    perf.start_update_time()
    current_effect.update(elapsed_time)
    perf.add_update_time()

    perf.start_render_time()
    output = PixelBuffer(NUM_LEDS)
    current_effect.render(output)
    for led_index in range(NUM_LEDS):
        pixels[led_index] = output[led_index]
    perf.add_render_time()

    pixels.show()

    if perf.complete_frame():
        frames = perf.frame_count
        fps = frames / (perf.last_frame_end - perf.start_time)
        print(
            f"FPS: {fps:.2f}, "
            f"Update Time: {perf.update_time_total / frames:.4f}s, "
            f"Render Time: {perf.render_time_total / frames:.4f}s, "
            f"Mem Delta Avg: {perf.memory_delta_total / frames:.2f}B, "
            f"Mem Delta Peak: {perf.memory_delta_peak}B, "
            f"Mem Free: {perf.last_mem_free}B, "
            f"Frame Time Peak: {perf.frame_time_peak:.4f}s"
        )

    if current_time > next_change_time:
        level_index += 1
        if level_index >= len(SAMPLE_LEVELS):
            level_index = 0
            element_index = (element_index + 1) % len(element_names)
            current_element = element_names[element_index]
        current_level = SAMPLE_LEVELS[level_index]
        print(f"Element: {current_element}, Level: {current_level}")
        current_effect = create_effect(current_element, current_level)
        gc.collect()
        next_change_time = current_time + DISPLAY_SECONDS
