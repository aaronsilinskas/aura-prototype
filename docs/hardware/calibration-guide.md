# Capacity Model Calibration Guide

How the measured constants in [`capacity-model.md`](capacity-model.md) are produced
on real hardware. The model doc holds the formulas, the resource summary, and the
filled-in constant tables; this guide holds the *mechanics* of profiling — what each
profiler under `examples/hardware/profiling/` sweeps and how to read its output into
the matching table.

Each profiler computes its target table's constants on-device and prints a
**paste-ready markdown row**, so values are never eyeballed from raw stats lines.
Copy the emitted row into the matching table in `capacity-model.md`.

## Emitting rows from profilers

Each row is preceded by a greppable marker line naming its target table:

```
__TABLE_ROW table=engine_component_costs
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.1234 | 0.0456 | 0.0789 | _TBD_ |
```

- The shared `print_table_row` helper (`hardware/shared/profiling_helpers.py`)
  prepends the `(board, runtime, driver)` key every table shares; the profiler
  supplies the component-specific cells.
- Slopes and intercepts (per-rule, per-pixel, per-voice costs and their fixed terms)
  are fit on-device with `linear_fit` over the sweep.
- Cells a bare board cannot measure — e.g. IR-rx `max_frame_ms` with no external
  packet source, or IR-tx `cost_ms` whose average depends on an unswept send cadence
  — are emitted as the literal `_TBD_` so the row stays paste-ready with its gaps
  explicit.

## `baseline_profiler.py` — board profiles & per-MCU baselines

Feeds the **Board profiles** and **Per-MCU baselines** tables.

- `total_free_heap_bytes` is its `gc.mem_free()` reading (the "Mem Free" stats line).
- `engine-host` mode profiles the rule-less `GameEngine.update(state)` tick; its
  `cpu_percent` is the engine-host baseline. `satellite` mode profiles the bare
  framework loop with no engine.
- The `heap_bytes` it reports is the **bare** framework (empty registry, no packs,
  no scene). A real prop also loads a scene, which dominates its heap.
- `MODE = "scene_content"` (finer `__SCENE_STAGES` snapshots + a `BALLAST_BYTES`
  free-heap test) is the headless investigation mode for scene memory — useful for
  relative comparisons and scene-graph debugging, but its absolute figure is an
  artifact (~2× over-count; see the scene-content gap note in `capacity-model.md`).

## `engine_profiler.py` — engine component costs

Drives the real `GameEngine.update(state)` dispatch loop with a synthetic
`_ProfilerRule` / `_ProfilerEvent` pair, sweeping `rule_count` and `events_per_tick`
as independent axes (each holding the other at a fixed reference of 1). Cells:

- **`tick_fixed_ms`** — the `(rule_count=0, events_per_tick=0)` point's average Update
  Time: the fixed cost of one tick with no rules and no queued events.
- **`per_rule_ms`** — `linear_fit` slope of average Update Time vs `rule_count` across
  `RULE_COUNTS`, with `events_per_tick` held at 1.
- **`per_event_ms`** — `linear_fit` slope of average Update Time vs `events_per_tick`
  across `EVENTS_PER_TICK_VALUES`, with `rule_count` held at 1.

`router_overhead_ms` is out of scope for this profiler: it is the cost of shipping
commands from the engine host to remote satellite MCUs, which has no seam inside the
`GameEngine.update` tick loop. The cell stays `_TBD_` pending a counting network stub
or analytic seeding.

> Two durable caveats this profiler exposes are recorded in `capacity-model.md`'s
> engine cost-model section: the additive-vs-product dispatch approximation, and the
> `tick_fixed_ms` ↔ engine-host-baseline overlap (don't double-charge).

## `pixel_profiler.py` — pixel scope costs & memory

Sweeps `pixel_count`, effect identity, and `stack_depth`. Because
`cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms`,
per-frame cost is linear in `stack_depth * pixel_count`: the `linear_fit` **slope** is
`worst_case_effect_per_pixel_ms` and the **intercept** is the fixed `flush_ms` (so no
separate flush-timing seam is needed — `effect_manager.update` renders and flushes in
one call). The profiler fits each effect element independently and reports the
**worst-case element's** slope, with that element's intercept as `flush_ms`.

For the **memory** table it snapshots free heap before building the scope and measures
the delta after the full sweep (`gc.collect()` on both sides), so the figure includes
the output object, its driver, and the per-scope `PixelBuffer`s. The shared
`PackRegistry` is built once before the loop and excluded; the `EffectManager`
baseline lands in the fixed `footprint_base_bytes` intercept.

### Matrix driver: buffered vs. no-buffer and the I2C transaction boundary

The IS31FL3741 driver runs **buffered** (`allocate=MUST_BUFFER`, the default in
`propmaker.setup_matrix_is31fl3741`) or **no-buffer**:

- **Buffered**: accumulates pixel writes in RAM, flushes in a single I2C burst at
  `show()`, so `flush_ms` dominates and `worst_case_effect_per_pixel_ms` is low.
- **No-buffer**: each `pixel()` call sends a small I2C transaction immediately,
  scattering traffic across the render pass before `show()`.

To capture both, the profiler counts bytes across the **entire**
`effect_manager.update()` tick (render + flush) via a `CountingI2C` decorator wrapping
the real bus. `i2c_transaction_bytes` is that whole-tick byte count at the worst-case
(largest) pixel count; byte volume is independent of stack depth and effect identity,
so no separate I2C sweep axis is needed.

## `sound_profiler.py` — sound component costs & memory

Sweeps `concurrent_voices`. Because
`cost_ms = mixer_fixed_ms + per_voice_ms * effective_voices`, the `linear_fit`
**intercept** is `mixer_fixed_ms` and the **slope** is `per_voice_ms`.

For memory it measures a `gc.mem_free()` delta around construction (idle, before any
voice is claimed), keyed by `num_voices`. The output has no deinit (it owns the I2S
pins), so it is built exactly once per run; run at additional `num_voices` values to
record the scaling. The module-load heap is paid by an import-only warm-up before the
snapshot.

## `vibration_profiler.py` — vibration component costs & memory

`cost_ms` is the measured average per-event CPU cost of `handle_event` +
`motor.play()`. `i2c_transaction_bytes` is measured on-device by wrapping the real
`busio.I2C` bus in a `CountingI2C` decorator before `setup_drv2605`, resetting the
counter before a representative vibration event, and reading `bytes_written` after.

For memory it measures a `gc.mem_free()` delta around construction (a single value —
nothing scales). The shared I2C bus (also used by the matrix and accelerometer) is
built before the snapshot and excluded; the driver-module import is pre-paid by an
import-only warm-up.

## `ir_tx_profiler.py` — IR-transmit component costs & memory

Sweeps `PAYLOAD_LENGTHS`. `blocking_send_ms` recorded in the table is the realistic
4-byte AURA payload's `PulseOut.send` blocking duration; the worst-case across the
full sweep (longest payload) measures ~757.81 ms — use that only if a prop transmits
much longer payloads. `cost_ms` (the average per-frame reservation) is not swept; it
is derived from `blocking_send_ms` and the send cadence (see the IR-transmit cost
model in `capacity-model.md`).

For memory it measures a `gc.mem_free()` delta around construction of the transmitter
path only (LINE `PulseOut` + `InfraredTransmitter` + `HardwareNetworkControls`) — the
receiver's `PulseIn(maxlen=256)` is excluded (it is the separate IR-rx component).

## `ir_rx_profiler.py` — IR-receive deadline & memory

Uses the **tunable-injected-load technique**: an artificial per-frame busy-loop
(`INJECTED_LOAD_MS`) is swept upward (`INJECTED_LOAD_SWEEP_MS`) to simulate co-located
CPU load while a known incoming packet rate is induced via loopback from an IR
transmitter or a second board (`ir_rx_packet_source.py`). The profiler counts
sequence-number gaps to compute a packet-loss rate; `max_frame_ms` is the peak frame
time (`PerformanceTracker.frame_time_peak`) at the **first injected-load point where
packet loss becomes non-zero** for the profiled `buffer_depth` (`PulseIn.maxlen`) and
`incoming_rate_hz`.

This requires an **external IR packet source**; on a bare board no packets arrive and
`max_frame_ms` is emitted as `_TBD_`.

For memory it measures a `gc.mem_free()` delta around the warmed single-receiver chain
(`PulseIn` + `PulseInReader` + `InfraredSingleReceiver` + decoder), sweeping
`PulseIn.maxlen`. The `PulseIn` ring buffer is on the GC heap but scales non-linearly
(see the IR-receive memory note in `capacity-model.md`).

## `tag_prop_profiler.py` — reference prop validation

Stands up the whole assembled reference `tag` prop on real hardware and emits a
`__TABLE_ROW table=reference_prop_validation` line (reservation%, footprint_B,
headroom%, peak_frame_ms) plus a `__PROP_BREAKDOWN` of staged `gc.mem_free()` deltas
(peripherals / registries / audio_outputs / engine / scene / total). The `scene`
stage is the in-situ first-tick scene-content figure (see the scene-content gap note
in `capacity-model.md`). `TARGET_FPS` is set to the prop's achievable single-MCU rate
so predicted and measured share one frame budget.
