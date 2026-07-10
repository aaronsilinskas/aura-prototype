"""In-situ scene-load profiler -- staged `load` / first-tick heap on the real prop.

This is the diagnostic half of the capacity teardown (#460): it stands up the
**real assembled prop** (IS31FL3741 matrix, I2S audio, DRV2605L vibration, and --
for scenes that use the network -- the IR LINE emitter + one IR receiver), loads a
named scene against those **real outputs**, and reports the heap consumed in two
headline stages (see "Hardware bring-up" below for the finer breakdown the
``__SCENE_STAGES`` line prints around them):

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

Hardware bring-up
------------------
Each ``HARNESSES`` entry describes a ``DeviceConfig`` built **in-file** (not read
from ``aura-device.json``) and handed to
``hardware.circuitpython.device_builder.build_hardware`` -- the same assembly path
production demos use, so this profiler measures the same hardware graph a prop
actually runs. A harness with ``"ir": None`` omits the ``ir`` key from the mapping
entirely, so ``build_hardware`` wires **no** IR receiver and no network controls --
keeping them off the heap for scenes that never touch the network. ``"tag"`` and
``"default"`` include an ``ir`` section and pass the matching wire-frame codec.

Hardware
--------
This measures scene heap against the prop's **outputs** only; it does not read
buttons or the accelerometer (inputs do not allocate scene heap), even though
``build_hardware`` wires them up as part of the assembled bundle.

- Adafruit RP2040 PropMaker Feather
- Adafruit IS31FL3741 13x9 RGB LED Matrix Breakout (I2C on default SDA/SCL)
- DRV2605L haptic motor driver on default SDA/SCL (optional -- the profiler runs
  without it, but the vibration output is then absent from the measurement)
- For scenes whose harness sets ``"ir"``: IR receiver on IR_RX_PIN_NAME and IR LINE
  emitter on IR_LINE_PIN_NAME

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

from effects.performance import PerformanceTracker
from engine.effects.manager import EffectManager
from engine.engine import GameEngine
from engine.packs import PackRegistry
from engine.scene import SceneManager, SceneRegistry
from engine.timer import Timer
from hardware.circuitpython.audio_output import AudioEffectOutput
from hardware.circuitpython.device_builder import build_hardware
from hardware.circuitpython.drv2605_output import Drv2605EffectOutput
from hardware.circuitpython.is31fl3741_output import (
    IS31FL3741_COLS,
    IS31FL3741_SCOPE_ROWS,
    IS31FL3741EffectOutput,
)
from hardware.shared.device_config import DeviceConfig, parse_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.ir_protocol import InfraredDecoder, InfraredEncoder
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

# Button pins -- build_hardware always wires buttons, though this profiler never
# reads them (inputs do not allocate scene heap). Match the production demo.
BUTTON_A_PIN_NAME: Final = "GP14"
BUTTON_B_PIN_NAME: Final = "GP15"

# IR transceiver pin names -- update these to match your board layout. Only used
# for harnesses whose "ir" is not None (tag, hardware_test); ignored otherwise.
IR_RX_PIN_NAME: Final = "GP16"
IR_LINE_PIN_NAME: Final = "GP17"

# I2S amp pins -- update these to match your board layout. Declared directly
# in each harness's audio section (see _device_config_for), resolved against
# the real `board` module by build_hardware the same way every other
# configured pin is.
I2S_BIT_CLOCK_PIN_NAME: Final = "GP10"
I2S_WORD_SELECT_PIN_NAME: Final = "GP11"
I2S_DATA_PIN_NAME: Final = "GP12"

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
            "go_start": "sounds/blip.wav",
            "game_over_sting_start": "sounds/game_over.wav",
            "fire_shot_start": "sounds/blip.wav",
            "scene.hit_start": "sounds/blip.wav",
            "reload": "sounds/blip.wav",
            "reload_complete": "sounds/blip.wav",
        },
        "num_voices": 4,
        "ir": "tag",
    },
    # examples/hardware/scene_demo.py (scene="red_light_green_light")
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
    # examples/hardware/scene_demo.py (scene="hardware_test")
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


def _device_config_for(harness: dict) -> DeviceConfig:
    """Build the in-file DeviceConfig for `harness` via parse_device_config.

    Mirrors the matrix geometry every prop in this repo ships (IS31FL3741_COLS /
    IS31FL3741_SCOPE_ROWS) and the harness's own audio clips/voice count. Omits
    the ``ir`` key entirely when ``harness["ir"]`` is ``None`` so build_hardware
    wires no IR receiver and no network controls for scenes that never touch the
    network -- ``HARNESSES`` stays the single source of truth for what each scene
    needs, not a static ``aura-device.json``.
    """
    mapping: dict = {
        "pixels": [
            {
                "type": "matrix",
                "cols": IS31FL3741_COLS,
                "scope_rows": {
                    key: [scope_range.start, scope_range.stop]
                    for key, scope_range in IS31FL3741_SCOPE_ROWS.items()
                },
            }
        ],
        "buttons": [BUTTON_A_PIN_NAME, BUTTON_B_PIN_NAME],
        "audio": {
            "voices": harness["num_voices"],
            "max_volume": 0.1,
            "clips": harness["audio_clips"],
            "i2s_bit_clock": I2S_BIT_CLOCK_PIN_NAME,
            "i2s_word_select": I2S_WORD_SELECT_PIN_NAME,
            "i2s_data": I2S_DATA_PIN_NAME,
        },
    }
    if harness["ir"] is not None:
        mapping["ir"] = {"rx": IR_RX_PIN_NAME, "line": IR_LINE_PIN_NAME}
    return parse_device_config(mapping)


def _ir_codec_for(harness: dict) -> tuple[InfraredEncoder | None, InfraredDecoder | None]:
    """Return the (encoder, decoder) pair build_hardware should use for `harness`.

    ``"tag"`` measures against the TagInfrared* wire-frame; ``"default"`` returns
    ``(None, None)`` so build_hardware falls back to its own Aura wire-frame
    default. Harnesses with ``"ir": None`` never reach build_hardware's IR branch
    (the config carries no ``ir`` section), so the codec choice is irrelevant and
    also returns ``(None, None)``.
    """
    if harness["ir"] == "tag":
        return TagInfraredEncoder(), TagInfraredDecoder()
    return None, None


def _verify_hardware(hw: DeviceHardware, harness: dict) -> None:
    """Fail loud if the assembled bundle is missing an output this harness expects.

    A silent gap here (e.g. build_hardware skipping the matrix because the I2C bus
    misbehaved) would otherwise surface only as a confusing, wrong heap figure --
    this raises immediately instead so a bad run is never mistaken for a valid
    baseline.
    """
    if not any(isinstance(output, IS31FL3741EffectOutput) for output in hw.outputs):
        raise RuntimeError("build_hardware bundle is missing the IS31FL3741 matrix output")
    if not any(isinstance(output, AudioEffectOutput) for output in hw.outputs):
        raise RuntimeError("build_hardware bundle is missing the audio output")
    if harness["ir"] is None:
        if hw.ir_receiver is not None:
            raise RuntimeError("harness declares ir=None but build_hardware wired an IR receiver")
    elif hw.ir_receiver is None:
        raise RuntimeError(f"harness ir={harness['ir']!r} but build_hardware wired no IR receiver")


def _build_prop(scene_name: str, harness: dict) -> tuple[SceneManager, EffectManager, Timer]:
    """Stand up the real prop for `harness` and load `scene_name` in situ.

    Mirrors the production demo for each scene (matrix + audio + optional motor +
    optional IR/network controls) via the single ``build_hardware`` call, then
    loads the scene against those real outputs and applies its first tick.
    build_hardware imposes a coarser boundary than the old per-driver setup calls
    did, so the staged free-heap breakdown is now: one hardware-bundle delta
    (the whole build_hardware call), then the stages this profiler still owns
    individually -- registry scan, engine/manager construction, scene load, and
    first tick. Prints the staged ``__SCENE_STAGES`` breakdown plus the
    paste-ready ``scene_in_situ_baselines`` row. Returns the live driving objects
    so the caller can keep ticking the scene for observation.
    """
    config = _device_config_for(harness)
    ir_encoder, ir_decoder = _ir_codec_for(harness)

    gc.collect()
    free_before_hardware = gc.mem_free()
    hw = build_hardware(
        config,
        board,
        ir_encoder=ir_encoder,
        ir_decoder=ir_decoder,
        i2c=board.STEMMA_I2C(),
    )
    gc.collect()
    free_after_hardware = gc.mem_free()
    _verify_hardware(hw, harness)

    effect_registry = PackRegistry(item_attr="BUILD")
    effect_registry.scan_dir("packs/effects", "packs.effects")
    rule_registry = PackRegistry(item_attr="RULE")
    rule_registry.scan_dir("packs/rules", "packs.rules")
    scene_registry = SceneRegistry()
    scene_registry.scan_dir("packs/scenes", "packs.scenes")
    gc.collect()
    free_after_registries = gc.mem_free()

    effect_manager = EffectManager(registry=effect_registry, outputs=hw.outputs)
    timer = Timer()
    engine = GameEngine(
        effect_controls=effect_manager,
        timer=timer,
        network_controls=hw.network_controls,
    )
    manager = SceneManager(
        engine, effect_registry, rule_registry, scene_registry, effect_admin=effect_manager
    )
    gc.collect()
    free_after_engine = gc.mem_free()

    manager.load(scene_name)
    gc.collect()
    free_after_load = gc.mem_free()

    manager.update()  # applies the load transition; the scene's first tick fires
    gc.collect()
    free_after_tick = gc.mem_free()

    hardware_bytes = free_before_hardware - free_after_hardware
    registries_bytes = free_after_hardware - free_after_registries
    engine_bytes = free_after_registries - free_after_engine
    load_bytes = free_after_engine - free_after_load
    first_tick_bytes = free_after_load - free_after_tick
    motor_present = any(isinstance(output, Drv2605EffectOutput) for output in hw.outputs)

    print(
        f"__SCENE_STAGES scene={scene_name}, motor_present={motor_present}, "
        + f"hardware={hardware_bytes}, registries={registries_bytes}, "
        + f"engine={engine_bytes}, load={load_bytes}, first_tick={first_tick_bytes}, "
        + f"free_after_tick={free_after_tick}"
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
            f"No harness defined for SCENE_NAME={SCENE_NAME!r}; add one to HARNESSES "
            + f"(have: {list(HARNESSES.keys())})"
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
