"""Reference prop + board profiles for end-to-end estimator validation (#401).

This is the *prediction* half of #401: it encodes the calibrated RP2040 PropMaker
board profile and the reference `tag` prop's actual loadout (IS31FL3741 matrix,
I2S audio, DRV2605L vibration, one IR LINE emitter + one IR receiver, two
buttons -- a single-MCU prop), then runs the estimator so the predicted CPU
reservation, headroom, achievable FPS, and memory footprint can be compared
against the measured values from
`examples/hardware/profiling/tag_prop_profiler.py`.

All constants are sourced from `docs/hardware/capacity-model.md`. Cells the doc
still carries as `_TBD_` (router overhead, IR-tx average cost, IR-rx incoming
rate, and -- critically -- every component's `memory_footprint_bytes`) are set
to 0 here and flagged via `uncalibrated=True` so the runner can call out which
predictions rest on real measurements vs. uncalibrated gaps.

Run the prediction with:

    python -m scripts.capacity.reference_props
"""

from __future__ import annotations

import math

from scripts.capacity.estimator import assign
from scripts.capacity.profiles import (
    BoardProfile,
    EngineComponent,
    IrTransmitComponent,
    McuBaseline,
    PixelScopeComponent,
    PropProfile,
    ReceiverComponent,
    SimpleComponent,
    SoundComponent,
    VibrationComponent,
)

# ---------------------------------------------------------------------------
# Calibrated board profile (capacity-model.md, circuitpython_10_0_3)
# ---------------------------------------------------------------------------

# `target_fps` is the 24 FPS *ceiling*; a prop with an IS31FL3741 scope cannot
# hold it (the ~60 ms flush alone exceeds the 41.7 ms budget). `achievable_fps`
# below derives the rate this prop actually sustains.
#
# Constants are the `circuitpython_10_2_1` rows -- the runtime the capacity doc's
# "Realistic target tick rate" worked example currently uses. If the reference
# prop runs `10_0_3`, swap in that runtime's rows (baselines 4.75%/4.50%, engine
# per_rule 0.0621 / per_event 0.1177, matrix 0.103225/59.2329, sound
# 0.1834/0.0521, vibration 7.4870) and regenerate.
RP2040_PROPMAKER_BOARD = BoardProfile(
    name="adafruit_feather_rp2040_prop_maker",
    runtime="circuitpython_10_2_1",
    target_fps=24.0,
    peripherals=("i2c", "i2s", "pwm"),
    total_free_heap_bytes=129_536,
    engine_host_baseline=McuBaseline(cpu_percent=5.65, heap_bytes=656),
    satellite_baseline=McuBaseline(cpu_percent=5.21, heap_bytes=464),
    headroom_reserve_percent=20.0,
    # baseline_profiler.py showed ~23 KB of GC churn on this runtime.
    gc_margin_bytes=23_000,
)

# ---------------------------------------------------------------------------
# Reference `tag` prop loadout (capacity-model.md constants tables)
# ---------------------------------------------------------------------------

# Matrix is the Adafruit IS31FL3741 13x9 breakout -> 117 pixels, all scopes
# composited onto the one matrix (a single PixelScopeComponent).
MATRIX_PIXEL_COUNT = 13 * 9

# Worst-case concurrent effect layers composited on the matrix in the Playing
# phase (progress + ammo bars with a transient hit/fire/reload layer). A
# scene-derived estimate -- raise it to probe a heavier stack.
MATRIX_STACK_DEPTH = 2

# Tag scene rule count (one RULE per phase: ready/starting/playing/shooting/
# hit/game_over) and the worst-case events dispatched per tick (the per-frame
# ButtonAndAcceleration input event, plus an IRReceived event on a hit frame).
TAG_RULE_COUNT = 6
TAG_EVENTS_PER_TICK = 2

# AudioEffectOutput is built with num_voices=4 in the tag prop; the scene can
# stack at most that many concurrent voices.
TAG_NUM_VOICES = 4

# IR receiver PulseIn is allocated with maxlen=256 (propmaker.setup_ir).
IR_BUFFER_DEPTH = 256


def tag_reference_prop() -> PropProfile:
    """Build the reference `tag` prop's component list for the estimator.

    `EngineComponent.tick_fixed_ms` is set to 0 here, not its calibrated
    0.0694 ms: the capacity doc's `tick_fixed_ms <-> engine-host baseline
    overlap` note warns the fixed per-tick engine cost is already folded into
    the 2.35% engine-host baseline, so charging both would double-count it. Only
    the marginal per-rule / per-event terms are charged on top of the baseline.
    """
    engine = EngineComponent(
        name="tag-engine",
        tick_fixed_ms=0.0,  # folded into engine-host baseline (see docstring)
        per_rule_ms=0.0565,
        per_event_ms=0.1147,
        router_overhead_ms=0.0,  # _TBD_ in doc; remote_mcus=0 so it never applies
        rules=TAG_RULE_COUNT,
        events_per_tick=TAG_EVENTS_PER_TICK,
        remote_mcus=0,  # single-MCU prop: no satellites to route to
    )
    matrix = PixelScopeComponent(
        name="matrix-scope",
        driver="is31fl3741_matrix",
        pixel_count=MATRIX_PIXEL_COUNT,
        worst_case_effect_per_pixel_ms=0.105998,
        flush_ms=60.6856,
        stack_depth=MATRIX_STACK_DEPTH,
        # i2c_bandwidth_bytes_per_sec ~= 8664.0 in the doc; reproduced as
        # transaction_bytes * frequency. No i2c bus budget is declared, so this
        # is informational only (not a feasibility constraint here).
        i2c_transaction_bytes=361,
        i2c_frequency_hz=24.0,
    )
    sound = SoundComponent(
        name="sound",
        mixer_fixed_ms=0.1929,
        per_voice_ms=0.0425,
        num_voices=TAG_NUM_VOICES,
        max_concurrent_voices=TAG_NUM_VOICES,
    )
    vibration = VibrationComponent(
        name="vibration",
        cost_ms=7.0801,
        max_calls_per_minute=6.0,
        i2c_transaction_bytes=18,  # reproduces the doc's ~1.80 B/s bus share
    )
    ir_tx = IrTransmitComponent(
        name="ir-tx-line",
        cost_ms=0.50,  # realistic 4-byte AURA payload at 0.2 Hz cadence (doc)
        blocking_send_ms=59.57,  # 4-byte payload PulseOut.send (not the 757 max)
    )
    # One IR receiver (this prop's actual loadout -- a subset of the fixed-4
    # design maximum). incoming_rate_hz left at 0: the model's derived
    # max_frame_ms = buffer_depth / incoming_rate * 1000 does NOT match the doc's
    # *measured* deadline (buffer_depth=64, incoming_rate=13.9 -> the model would
    # give ~4600 ms, but the profiler measured ~63 ms at packet-loss onset). That
    # tension is a model gap to validate on hardware (see capacity-model.md
    # "Reference prop validation"), so no hard deadline is asserted here.
    ir_rx = ReceiverComponent(
        name="ir-rx",
        cost_ms=0.0,  # fixed_drain _TBD_ in doc
        base_footprint_bytes=0,  # _TBD_ (uncalibrated memory footprint)
        bytes_per_buffer_slot=0,  # _TBD_
        buffer_depth=IR_BUFFER_DEPTH,
        incoming_rate_hz=0.0,
        uncalibrated=True,
    )
    # LIS3DH accelerometer: one I2C read per tick. cost_ms ~0 (a single read);
    # carried so the loadout is complete.
    accelerometer = SimpleComponent(
        name="accelerometer",
        cost_ms=0.0,
        i2c_transaction_bytes=6,
        i2c_frequency_hz=24.0,
        uncalibrated=True,
    )
    return PropProfile(
        name="tag-reference-prop",
        components=[engine, matrix, sound, vibration, ir_tx, ir_rx, accelerometer],
    )


def _engine_host_cost_ms(prop: PropProfile) -> float:
    """Summed per-frame cost (ms) of every component, i.e. the single-MCU load.

    For a single-MCU prop every component lands on the engine-host, so the
    busiest-MCU cost the achievable FPS derives from is just the total.
    """
    return sum(component.cost_ms for component in prop.components)


def achievable_fps(prop: PropProfile, board: BoardProfile) -> float:
    """Highest FPS the single busiest MCU can sustain, capped at the board ceiling.

    Inverts the packing inequality exactly as the capacity doc's "Realistic
    target tick rate" section does:

        required_frame_budget_ms = Sigma(cost_ms) / usable_fraction
        achievable_fps           = min(ceiling, 1000 / required_frame_budget_ms)
    """
    usable_fraction = (
        100.0 - board.engine_host_baseline.cpu_percent - board.headroom_reserve_percent
    ) / 100.0
    required_budget_ms = _engine_host_cost_ms(prop) / usable_fraction
    return min(board.target_fps, 1000.0 / required_budget_ms)


def flat_out_fps(prop: PropProfile, board: BoardProfile) -> float:
    """Highest FPS the busiest MCU can sustain with **no** headroom reserve held back.

    `achievable_fps` deducts `headroom_reserve_percent` (the design margin); a
    profiler that runs the loop unpaced instead reports the *flat-out* rate, which
    only deducts the role baseline. Compare the profiler's measured FPS against
    this figure, not against the reserved design rate.
    """
    usable_fraction = (100.0 - board.engine_host_baseline.cpu_percent) / 100.0
    required_budget_ms = _engine_host_cost_ms(prop) / usable_fraction
    return min(board.target_fps, 1000.0 / required_budget_ms)


def _amortized_cost_ms(
    component: (
        EngineComponent
        | SimpleComponent
        | ReceiverComponent
        | PixelScopeComponent
        | SoundComponent
        | VibrationComponent
        | IrTransmitComponent
    ),
    fps: float,
) -> float:
    """Per-frame cost with sparse-event components spread over their duty cycle.

    The packer charges `VibrationComponent.cost_ms` (~7 ms) on *every* frame -- the
    safe worst-case assumption for feasibility/headroom. But the haptic motor fires
    at most `max_calls_per_minute` (6/min on the tag prop), and the unpaced profiler
    reports the *mean* steady-state busy time, where that cost is amortized to near
    zero. Charging it every frame over-states the predicted average reservation by
    ~7 ms -- the entire #401 reservation gap. For the average comparison only, spread
    the haptic cost across the frames between firings:

        amortized_ms = cost_ms * (max_calls_per_minute / 60) / fps

    Every other component runs every frame (matrix flush, sound mixer, ...) and is
    charged in full. This does NOT touch the packer's worst-case behavior; it is a
    comparison-only adjustment local to #401.
    """
    if isinstance(component, VibrationComponent):
        calls_per_frame = (component.max_calls_per_minute / 60.0) / fps
        return component.cost_ms * calls_per_frame
    return component.cost_ms


def amortized_engine_host_cost_ms(prop: PropProfile, fps: float) -> float:
    """Summed per-frame cost (ms) with sparse-event components amortized (see `_amortized_cost_ms`).

    This is the figure to compare against the profiler's *average* reservation; the
    worst-case `_engine_host_cost_ms` is what the packer reserves for headroom.
    """
    return sum(_amortized_cost_ms(c, fps) for c in prop.components)


def predicted_worst_case_frame_ms(prop: PropProfile, fps: float) -> float:
    """Predicted worst single frame: the steady (amortized) frame plus the IR-tx blocking send.

    The peak frame is the IR-send frame -- `PulseOut.send` blocks for
    `blocking_send_ms` on top of the normal per-frame work (`IrTransmitComponent.
    blocking_send_ms`, a soft cost not folded into the average `cost_ms`). Every
    per-frame term (matrix flush, per-pixel at the worst-case `stack_depth`, sound)
    is charged in full; only the sparse haptic event is amortized -- a vibration is
    not assumed to coincide with the worst send frame. Compare against the profiler's
    `frame_time_peak`.
    """
    blocking_ms = sum(
        c.blocking_send_ms for c in prop.components if isinstance(c, IrTransmitComponent)
    )
    return amortized_engine_host_cost_ms(prop, fps) + blocking_ms


def _board_at_fps(board: BoardProfile, fps: float) -> BoardProfile:
    """Return a copy of `board` with `target_fps` set to `fps` (for the comparison run)."""
    return BoardProfile(
        name=board.name,
        runtime=board.runtime,
        target_fps=fps,
        peripherals=board.peripherals,
        total_free_heap_bytes=board.total_free_heap_bytes,
        engine_host_baseline=board.engine_host_baseline,
        satellite_baseline=board.satellite_baseline,
        headroom_reserve_percent=board.headroom_reserve_percent,
        gc_margin_bytes=board.gc_margin_bytes,
        bus_budgets=board.bus_budgets,
        peripheral_budgets=board.peripheral_budgets,
    )


def main() -> None:
    """Print the estimator's prediction for the reference tag prop."""
    prop = tag_reference_prop()
    board = RP2040_PROPMAKER_BOARD

    total_cost_ms = _engine_host_cost_ms(prop)
    fps = achievable_fps(prop, board)

    print(f"Reference prop : {prop.name}")
    print(f"Board          : {board.name} / {board.runtime}")
    print(f"Components      : {len(prop.components)}")
    print(f"Total cost/frame: {total_cost_ms:.2f} ms (single-MCU engine-host load)")
    print()

    # At the 24 FPS ceiling the matrix flush alone busts the budget -- show the
    # infeasible result, then the result at the prop's achievable rate.
    ceiling = assign(prop, board)
    print(f"At {board.target_fps:.0f} FPS ceiling (budget {board.frame_budget_ms:.1f} ms):")
    if ceiling.feasible:
        print(f"  feasible on {len(ceiling.mcus)} MCU(s)")
    else:
        print(f"  INFEASIBLE [{ceiling.conflict_type}] -- {ceiling.reason}")
    print()

    # Floor to a whole FPS for the single-MCU comparison: at the exact
    # achievable rate the 20% reserve leaves ~0 headroom, so a knife-edge
    # rounding artifact can spill the cheapest component onto a second MCU.
    # Flooring gives real slack and a clean TARGET_FPS for the profiler.
    comparison_fps = float(math.floor(fps))
    comparison_board = _board_at_fps(board, comparison_fps)
    result = assign(prop, comparison_board)
    budget_ms = comparison_board.frame_budget_ms
    print(
        f"Achievable single-MCU rate: {fps:.1f} FPS; "
        f"comparing at {comparison_fps:.0f} FPS (budget {budget_ms:.1f} ms)"
    )
    if not result.feasible:
        print(f"  INFEASIBLE [{result.conflict_type}] -- {result.reason}")
        return

    print(f"  feasible on {len(result.mcus)} MCU(s):")
    for mcu in result.mcus:
        reserved = sum(c.reserved_percent for c in mcu.components)
        print(
            f"  - {mcu.role}: reservation={reserved:.2f}%, "
            f"headroom={mcu.remaining_headroom_percent:.2f}%, "
            f"free_heap={mcu.remaining_heap_bytes:.0f} B"
        )
        for c in mcu.components:
            flag = " (uncalibrated)" if c.uncalibrated else ""
            print(f"      {c.name}: {c.reserved_percent:.2f}%{flag}")

    # Amortized comparison: the packer's reservation above charges vibration's
    # full ~7 ms every frame (worst case), but the unpaced profiler reports the
    # *mean* busy time, where the <=6 calls/min haptic cost is spread thin. These
    # are the apples-to-apples figures to compare against the profiler row.
    usable_cpu = 100.0 - board.engine_host_baseline.cpu_percent - board.headroom_reserve_percent
    amortized_cost = amortized_engine_host_cost_ms(prop, comparison_fps)
    amortized_reservation = amortized_cost / budget_ms * 100.0
    amortized_headroom = usable_cpu - amortized_reservation
    print()
    print(
        f"Amortized comparison @ {comparison_fps:.0f} FPS (vibration spread over its duty cycle):"
    )
    print(f"  reservation : {amortized_reservation:.2f}%  -- compare to profiler reservation%")
    print(f"  headroom    : {amortized_headroom:.2f}%  -- compare to profiler headroom%")
    print(
        f"  worst frame : {predicted_worst_case_frame_ms(prop, comparison_fps):.1f} ms "
        "-- compare to frame_time_peak"
    )
    print()
    print("Comparison figures for the unpaced profiler:")
    print(
        f"  flat-out FPS (no 20% reserve)   : {flat_out_fps(prop, board):.1f} "
        "-- compare to the profiler's measured FPS"
    )
    print()
    print("Predicted vs. measured -- run the on-device profiler and compare:")
    print(
        "  examples/hardware/profiling/tag_prop_profiler.py "
        f"(set TARGET_FPS = {comparison_fps:.0f})"
    )
    print(
        "Known model gap (acceptance criterion 4): component memory_footprint_bytes "
        "are still uncalibrated, so the predicted memory footprint is ~0 -- record "
        "the measured footprint and file a follow-up to calibrate it."
    )


if __name__ == "__main__":
    main()
