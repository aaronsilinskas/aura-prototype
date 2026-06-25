"""In-situ scene-load profiler -- staged `load` / first-tick heap on the real prop.

This is the diagnostic half of the capacity teardown (#460): it stands up the
**real assembled prop** (IS31FL3741 matrix, I2S audio, DRV2605L vibration, and --
for scenes that use the network -- the IR LINE emitter + one IR receiver), loads a
named scene against those **real outputs**, and reports the heap consumed in two
stages:

- **`load` delta** -- the heap `SceneManager.load(SCENE_NAME)` retains: the scene
  graph (phases, rules, effects) instantiated against the prop's registered scopes.
- **first-tick delta** -- the heap the first `SceneManager.update()` retains: the
  load transition is applied and the scene's opening effects fire for the first
  time (palettes/LUTs/buffers constructed, WAV files opened from flash).

Scene memory is **output-coupled** (the one #450 finding whose mechanism did not
survive but whose effect did), so a headless load -- against a `NullEffectOutput`
with no matrix buffers and no audio -- reports a different, misleading figure (the
old `baseline_profiler.py` `scene_content` mode produced a ~2x number and has been
removed). This profiler exists to measure the scene **in situ**, on the harness it
actually runs on.

What this tool is and is NOT
----------------------------
This is a **per-prop, scene-parameterized diagnostic** -- a tool for A/B comparing a
scene change against that scene's recorded baseline. It is **not** a feasibility
tool: it does not answer "will the prop fit". Only the whole-prop run
(`tag_prop_profiler.py`) answers that, because the parts do not sum to the whole.

!! THE HARNESS MUST MATCH THE SCENE !!
--------------------------------------
A recorded figure is valid **only for the `(scene, harness)` pair it was measured
against.** The harness -- which audio clips are registered, how many voices, and
whether the IR/network controls are present -- is configured **by hand** in the
``HARNESSES`` table below; this profiler does **not** auto-derive a scene's needs
from the scene itself.

Loading a scene against a mismatched harness (missing its audio clips, or missing
its targeted scopes/outputs) reproduces the exact headless-style artifact that
motivated this teardown: effects fail to resolve, and the first-tick allocation is
wrong. If you add or change a scene's clips/scopes, update its ``HARNESSES`` entry
to match, and re-record its baseline -- an old figure measured against a different
harness is not comparable.

Hardware
--------
This measures scene heap against the prop's **outputs** only; it does not read
buttons or the accelerometer (inputs do not allocate scene heap).

- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- DRV2605L haptic motor driver on default SDA/SCL (optional -- the profiler runs
  without it, but the vibration output is then absent from the measurement)
- For scenes whose harness sets ``"ir"``: IR receiver on IR_RX_PIN and IR LINE
  emitter on IR_LINE_PIN

Installation
------------
1. Install CircuitPython on your board:
   https://learn.adafruit.com/welcome-to-circuitpython/installing-circuitpython

2. Copy required libraries to CIRCUITPY/lib/:
     adafruit_is31fl3741/
     adafruit_lis3dh.mpy
     adafruit_drv2605.mpy  (optional - required only when a DRV2605L is wired up)

3. Run the deploy script to copy all source files and set code.py:
     python scripts/deploy.py examples/hardware/profiling/scene_load_profiler.py
   The board reboots and starts running automatically.

How to use
----------
- Set ``SCENE_NAME`` to the scene you want to measure (CircuitPython has no argv,
  so this is an edited constant). It must be a key of ``HARNESSES``.
- Confirm the matching ``HARNESSES`` entry describes the prop you are actually
  running on -- the clips registered, the voice count, and whether IR is wired.
- Read the ``__SCENE_STAGES`` line for the staged free-heap breakdown and the
  ``__TABLE_ROW table=scene_in_situ_baselines`` line for the paste-ready row to
  record in ``docs/hardware/recorded-metrics.md``.

Configuration
-------------
- SCENE_NAME: which scene (and therefore which ``HARNESSES`` entry) to measure.
- HARNESSES: per-scene harness definitions -- edit these to match your prop.
- LOG_INTERVAL_SECONDS: how often the post-load stats line is printed.
"""

from __future__ import annotations

import gc

import board

import hardware.circuitpython.propmaker as propmaker
from effects.performance import PerformanceTracker
from engine.audio import AudioRegistry
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.network import HardwareNetworkControls
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import (
    IS31FL3741_COLS,
    IS31FL3741_SCOPE_ROWS,
    IS31FL3741EffectOutput,
)
from hardware.shared.profiling_helpers import (
    print_profile_header,
    print_stats_line,
    print_table_row,
)
from hardware.shared.tag_protocol import TagInfraredDecoder, TagInfraredEncoder

try:
    from typing import Final
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration -- adjust to match your wiring
# ---------------------------------------------------------------------------

# IR transceiver pins -- update these to match your board layout. Only used for
# scenes whose harness sets ``"ir"`` (tag, hardware_test); ignored otherwise.
IR_RX_PIN: Final = board.D11
IR_LINE_PIN: Final = board.D12

LOG_INTERVAL_SECONDS: Final = 5.0

# Which scene to measure. CircuitPython has no argv, so edit this constant. It
# must be a key of HARNESSES below.
SCENE_NAME: Final = "tag"

# ---------------------------------------------------------------------------
# Per-scene harnesses -- the (scene, harness) pairs this prop can measure.
#
# Each entry mirrors that scene's production demo (the same clips, voice count,
# and network wiring the scene actually runs against). These are configured BY
# HAND, not derived from the scene: a recorded figure is only valid for the
# pairing described here. If a scene's clips or scopes change, update its entry
# and re-record its baseline.
#
# Keys:
#   audio_clips -- {effect_name: wav_path} registered in the AudioRegistry, so
#       the scene's sound effects resolve to real clips (mismatch = footgun).
#   num_voices  -- AudioEffectOutput voice count for this scene.
#   ir          -- IR/network harness: "tag" (TagInfrared* codec), "default"
#       (AuraInfrared* codec), or None (no IR receiver, no network controls).
# ---------------------------------------------------------------------------

HARNESSES: Final = {
    # examples/hardware/tag_demo.py / tag_prop_profiler.py
    "tag": {
        "audio_clips": {
            "warning_pulse_peak": "sounds/blip.wav",
            "game_over_sting_start": "sounds/game_over.wav",
            "fire_shot_start": "sounds/blip.wav",
            "scene.hit_start": "sounds/blip.wav",
            "reload": "sounds/blip.wav",
            "reload_complete": "sounds/blip.wav",
        },
        "num_voices": 4,
        "ir": "tag",
    },
    # examples/hardware/red_light_green_light_demo.py
    "red_light_green_light": {
        "audio_clips": {
            "ready_start": "sounds/red_light_green_light.wav",
            "warning_sting_peak": "sounds/blip.wav",
            "red_light_music_start": "sounds/rlgl_stop_music.wav",
            "green_light_music_start": "sounds/rlgl_go_music.wav",
            "game_over_sting_start": "sounds/game_over.wav",
            "win_sting_start": "sounds/game_won.wav",
            "level_up_start": "sounds/level_up.wav",
        },
        "num_voices": 2,
        "ir": None,
    },
    # examples/hardware/hardware_test_demo.py
    "hardware_test": {
        "audio_clips": {
            "sfx_test_start": "sounds/blip.wav",
        },
        "num_voices": 1,
        "ir": "default",
    },
}


def _harness_label(harness: dict) -> str:
    """Short, paste-ready descriptor of `harness` for the recorded-metrics row.

    Captures the dimensions that make a figure `(scene, harness)`-specific: the
    matrix + audio voice count, whether the haptic motor is present, and the IR
    codec (or its absence). The motor flag reflects the harness intent; the
    actual run also reports whether a DRV2605L was found (see ``__SCENE_STAGES``).
    """
    ir = harness["ir"]
    ir_part = "no-ir" if ir is None else f"ir({ir})"
    return f"matrix+audio(v{harness['num_voices']})+motor+{ir_part}"


def _setup_ir(harness: dict) -> tuple:  # (transmitters | None, receiver | None)
    """Build the IR transmitters + receiver for `harness`, or ``(None, None)``.

    Returns ``(None, None)`` for a harness with ``"ir": None`` so scenes that
    never touch the network are measured without a receiver or network controls
    on the heap -- part of keeping each figure faithful to its own harness.
    """
    mode = harness["ir"]
    if mode is None:
        return None, None
    if mode == "tag":
        encoder = TagInfraredEncoder()
        decoder = TagInfraredDecoder()
    else:  # "default" -- the AuraInfrared* codec propmaker installs by default
        encoder = None
        decoder = None
    return propmaker.setup_ir(
        IR_RX_PIN,
        IR_LINE_PIN,
        encoder=encoder,
        decoder=decoder,
    )


def _build_prop(scene_name: str, harness: dict) -> tuple[SceneManager, EffectManager, Timer]:
    """Stand up the real prop for `harness` and load `scene_name` in situ.

    Mirrors the production demo for each scene (matrix + audio + optional motor +
    optional IR/network controls), then loads the scene against those real
    outputs and applies its first tick. Snapshots free heap around the `load` and
    first-tick stages and prints the staged `__SCENE_STAGES` breakdown plus the
    paste-ready `scene_in_situ_baselines` row. Returns the live driving objects so
    the caller can keep ticking the scene for observation.
    """
    propmaker.setup_external_power()
    i2c = propmaker.setup_i2c()
    matrix = propmaker.setup_matrix_is31fl3741(i2c)
    motor = propmaker.setup_drv2605(i2c)
    ir_transmitters, _ir_receiver = _setup_ir(harness)

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")

    audio_registry = AudioRegistry()
    for effect_name, wav_path in harness["audio_clips"].items():
        audio_registry.register(effect_name, wav_path)
    audio_output = AudioEffectOutput(
        audio_registry,
        max_volume=0.1,
        num_voices=harness["num_voices"],
        i2s_bit_clock=board.I2S_BIT_CLOCK,
        i2s_word_select=board.I2S_WORD_SELECT,
        i2s_data=board.I2S_DATA,
    )

    outputs = [
        IS31FL3741EffectOutput(matrix, cols=IS31FL3741_COLS, scope_rows=IS31FL3741_SCOPE_ROWS),
        audio_output,
    ]
    if motor is not None:
        outputs.append(Drv2605EffectOutput(motor))
    effect_manager = EffectManager(registry=effect_registry, outputs=outputs)

    timer = Timer()
    network_controls = (
        HardwareNetworkControls(ir_transmitters) if ir_transmitters is not None else None
    )
    engine = GameEngine(
        effect_controls=effect_manager,
        timer=timer,
        network_controls=network_controls,
    )
    manager = SceneManager(engine, effect_registry, rule_registry, scene_registry)

    # Stage the two heap deltas the diagnostic reports. gc.collect on each side so
    # the figures are retained heap, not transient construction litter.
    gc.collect()
    free_before_load = gc.mem_free()

    manager.load(scene_name)
    gc.collect()
    free_after_load = gc.mem_free()

    manager.update()  # applies the load transition; the scene's first tick fires
    gc.collect()
    free_after_tick = gc.mem_free()

    load_bytes = free_before_load - free_after_load
    first_tick_bytes = free_after_load - free_after_tick

    print(
        "__SCENE_STAGES "
        f"scene={scene_name}, "
        f"motor_present={motor is not None}, "
        f"free_before_load={free_before_load}, "
        f"load={load_bytes}, "
        f"free_after_load={free_after_load}, "
        f"first_tick={first_tick_bytes}, "
        f"free_after_tick={free_after_tick}"
    )
    # Per-scene in-situ baseline: the (scene, harness) pair, its staged `load`
    # heap, and its first-tick heap. A standalone measurement -- not an additive
    # term, valid only for this pairing.
    print_table_row(
        "scene_in_situ_baselines",
        [scene_name, _harness_label(harness), load_bytes, first_tick_bytes],
    )
    return manager, effect_manager, timer


def run() -> None:
    """Measure SCENE_NAME's in-situ load/first-tick heap, then keep it ticking."""
    if SCENE_NAME not in HARNESSES:
        raise ValueError(
            f"No harness defined for SCENE_NAME={SCENE_NAME!r}; "
            f"add one to HARNESSES (have: {list(HARNESSES.keys())})"
        )
    harness = HARNESSES[SCENE_NAME]

    print_profile_header(
        component=f"scene_load.{SCENE_NAME}",
        sweep_axes=[],
        sweep_values=[],
        target_fps=0.0,
    )

    manager, effect_manager, timer = _build_prop(SCENE_NAME, harness)
    perf = PerformanceTracker(log_interval=LOG_INTERVAL_SECONDS)

    # The measurement is complete; the loop just keeps the scene live so the run
    # is observable (free heap holds steady, the device does not idle into a hang).
    while True:
        perf.start_frame()

        perf.start_update_time()
        timer.update()
        manager.update()
        effect_manager.update(timer)
        perf.add_update_time()

        if perf.complete_frame():
            print_stats_line(perf)


run()
