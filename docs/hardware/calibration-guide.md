# Hardware Profiler Runbook

How to run each profiler under `examples/hardware/profiling/` on real hardware and
where to record its output in [`recorded-metrics.md`](recorded-metrics.md). The metrics
doc holds the filled-in tables; this runbook holds the *mechanics* — what each profiler
sweeps, how to deploy it, and which table its emitted row feeds.

This is the doc where the future automated-profiling expansion will land.

## Deploying and capturing output

Each profiler is a CircuitPython example. Deploy it to a wired board and capture its
serial output with the deploy-watch tool (see [`../agents/deploy-watch.md`](../agents/deploy-watch.md)):

```
python -m scripts.deploy_watch examples/hardware/profiling/<profiler>.py \
    --until "__TABLE_ROW" --seconds 120
```

Several profilers have **config constants at the top of the module** that select what is
measured — edit them in the file before deploying:

- `baseline_profiler.py`: `MODE` (`"engine_host"` / `"satellite"`).
- `scene_load_profiler.py`: `SCENE_NAME` (which scene's `(scene, harness)` baseline to
  measure; must be a key of its `HARNESSES` table).
- `pixel_profiler.py`: `DRIVER` (`"neopixel_pwm"` / `"is31fl3741_matrix"`).
- `sound_profiler.py`: `NUM_VOICES` (re-run per voice count to record the scaling).
- The sweep arrays (`PIXEL_COUNTS`, `RULE_COUNTS`, `PAYLOAD_LENGTHS`, …) can be widened
  if a prop operates outside the default ranges.

## Reading the emitted row

Every profiler computes its target table's constants on-device and prints a
**paste-ready markdown row** via the shared `print_table_row` helper
(`hardware/shared/profiling_helpers.py`), so values are never eyeballed from raw stats
lines. Each row is preceded by a greppable marker naming its target table:

```
__TABLE_ROW table=engine_component_costs
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.1728 | 0.0565 | 0.1147 | _TBD_ |
```

- The helper prepends the `(board, runtime, driver)` key every table shares; the
  profiler supplies the component-specific cells.
- Slopes and intercepts (per-rule, per-pixel, per-voice costs and their fixed terms) are
  fit on-device with `linear_fit` over the sweep.
- Cells a bare board cannot measure — e.g. IR-rx `max_frame_ms` with no external packet
  source, or IR-tx `cost_ms` whose average depends on an unswept send cadence — are
  emitted as the literal `_TBD_` so the row stays paste-ready with its gaps explicit.

Copy the row into the matching table in [`recorded-metrics.md`](recorded-metrics.md).

> The profilers also emit per-component memory rows (`pixel_scope_memory`,
> `sound_component_memory`, etc.). `recorded-metrics.md` records only directly-measured
> whole-prop heap and per-scene in-situ baselines, so these per-component memory rows have
> **no destination table today** — they are inputs for the future automated-profiling
> expansion and can be ignored when recording isolation metrics now.

## `baseline_profiler.py` — board profiles & per-MCU baselines

Feeds the **Board profiles** and **Per-MCU baselines** tables.

- `total_free_heap_bytes` is its `gc.mem_free()` reading (the "Mem Free" stats line) on
  the **bare** framework (empty registry, no packs, no scene). A real prop also loads a
  scene, which dominates its heap.
- `engine_host` mode profiles the rule-less `GameEngine.update(state)` tick; its
  `cpu_percent` is the engine-host baseline. `satellite` mode profiles the bare
  framework loop with no engine.

> Per-scene heap is measured in situ by `scene_load_profiler.py` (below), **not** here. A
> headless scene load reports a misleading ~2× figure because scene memory is
> output-coupled, so `baseline_profiler.py` no longer offers a `scene_content` mode.

## `engine_profiler.py` — engine component costs

Feeds the **Engine component costs** table. Drives the real `GameEngine.update(state)`
dispatch loop with a synthetic `_ProfilerRule` / `_ProfilerEvent` pair, sweeping
`rule_count` and `events_per_tick` as independent axes (each holding the other at a
fixed reference of 1). Cells:

- **`tick_fixed_ms`** — the `(rule_count=0, events_per_tick=0)` point's average Update
  Time: the fixed cost of one tick with no rules and no queued events.
- **`per_rule_ms`** — `linear_fit` slope of average Update Time vs `rule_count` across
  `RULE_COUNTS`, with `events_per_tick` held at 1.
- **`per_event_ms`** — `linear_fit` slope of average Update Time vs `events_per_tick`
  across `EVENTS_PER_TICK_VALUES`, with `rule_count` held at 1.

`router_overhead_ms` is out of scope for this profiler: it is the cost of shipping
commands from the engine host to remote satellite MCUs, which has no seam inside the
`GameEngine.update` tick loop. The cell stays `_TBD_` pending a counting network stub.

> Two durable caveats this profiler exposes are noted alongside the engine cost table in
> `recorded-metrics.md`: the `per_rule_ms` / `per_event_ms` slopes are measured at a low
> cross-load (the real dispatch is `O(events × rules)`), and `tick_fixed_ms` overlaps
> the engine-host baseline (don't double-charge).

## `pixel_profiler.py` — pixel scope costs

Feeds the **Pixel scope costs** table. Sweeps `pixel_count`, effect identity, and
`stack_depth`. Because
`cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms`,
per-frame cost is linear in `stack_depth * pixel_count`: the `linear_fit` **slope** is
`worst_case_effect_per_pixel_ms` and the **intercept** is the fixed `flush_ms` (so no
separate flush-timing seam is needed — `effect_manager.update` renders and flushes in
one call). The profiler fits each effect element independently and reports the
**worst-case element's** slope, with that element's intercept as `flush_ms`.

### Matrix driver: buffered vs. no-buffer and the I2C transaction boundary

The IS31FL3741 driver runs **buffered** (`allocate=MUST_BUFFER`, the default in
`device_builder._setup_matrix_is31fl3741`) or **no-buffer**:

- **Buffered**: accumulates pixel writes in RAM, flushes in a single I2C burst at
  `show()`, so `flush_ms` dominates and `worst_case_effect_per_pixel_ms` is low.
- **No-buffer**: each `pixel()` call sends a small I2C transaction immediately,
  scattering traffic across the render pass before `show()`.

To capture both, the profiler counts bytes across the **entire**
`effect_manager.update()` tick (render + flush) via a `CountingI2C` decorator wrapping
the real bus. The byte volume is independent of stack depth and effect identity, so no
separate I2C sweep axis is needed. NeoPixel PWM is off the I2C bus and reports zero
bandwidth.

## `sound_profiler.py` — sound component costs

Feeds the **Sound component costs** table. Sweeps `concurrent_voices`. Because
`cost_ms = mixer_fixed_ms + per_voice_ms * effective_voices`, the `linear_fit`
**intercept** is `mixer_fixed_ms` and the **slope** is `per_voice_ms`. The output has no
deinit (it owns the I2S pins) so it is built exactly once per run; set `NUM_VOICES` and
re-run to record the cost at each voice cap.

## `vibration_profiler.py` — vibration component costs

Feeds the **Vibration component costs** table. `cost_ms` is the measured average
per-event CPU cost of `handle_event` + `motor.play()`. `i2c_transaction_bytes` is
measured on-device by wrapping the real `busio.I2C` bus in a `CountingI2C` decorator
before `setup_drv2605`, resetting the counter before a representative vibration event,
and reading `bytes_written` after.

## `ir_tx_profiler.py` — IR-transmit component costs

Feeds the **IR-transmit component costs** table. Sweeps `PAYLOAD_LENGTHS`.
`blocking_send_ms` recorded in the table is the realistic 4-byte AURA payload's
`PulseOut.send` blocking duration; the worst-case across the full sweep (longest
payload) measures ~757.81 ms — use that only if a prop transmits much longer payloads.
`cost_ms` (the average per-frame reservation) is not swept; it is derived from
`blocking_send_ms` and the send cadence (see the IR-transmit cost notes in
`recorded-metrics.md`).

## `ir_rx_profiler.py` — IR-receive deadline

Feeds the **IR-receive component deadline** table. Uses the **tunable-injected-load
technique**: an artificial per-frame busy-loop (`INJECTED_LOAD_MS`) is swept upward
(`INJECTED_LOAD_SWEEP_MS`) to simulate co-located CPU load while a known incoming packet
rate is induced via loopback from an IR transmitter or a second board
(`ir_rx_packet_source.py`). The profiler counts sequence-number gaps to compute a
packet-loss rate; `max_frame_ms` is the peak frame time
(`PerformanceTracker.frame_time_peak`) at the **first injected-load point where packet
loss becomes non-zero** for the profiled `buffer_depth` (`PulseIn.maxlen`) and
`incoming_rate_hz`.

This requires an **external IR packet source**; on a bare board no packets arrive and
`max_frame_ms` is emitted as `_TBD_`.

## `tag_prop_profiler.py` — whole-prop reference measurement

Feeds the **Reference `tag` prop** table under *Whole-prop measurements*. Builds an
in-file `TAG_HARNESS` device-config mapping (matrix + two buttons + IR + audio with 4
voices and 7 clips) and stands up the whole assembled reference `tag` prop through
`build_hardware` (the `TagInfrared*` codec is passed in), then emits a row with CPU
reservation %, total heap footprint, headroom %, and peak frame time, plus a
`__PROP_BREAKDOWN` of staged `gc.mem_free()` deltas re-shaped around the single
`build_hardware` call (hardware / registries / effect_manager / engine / scene / total)
for diagnostics. The matrix flush (~60 ms)
dominates the per-frame cost, so the prop cannot hold 24 FPS — set `TARGET_FPS` to the
rate the prop actually achieves (~7–13 FPS for any IS31FL3741 scope) so the recording is
taken at one frame budget. The profiler also reports its **measured** FPS so the chosen
budget can be sanity-checked against reality. Exercise the prop (fire shots, take hits)
to drive the peak frame time.

## `scene_load_profiler.py` — per-scene in-situ baselines

Feeds the **Per-scene in-situ baselines** table under *Whole-prop measurements*. Builds
an in-file `DeviceConfig` from the selected `HARNESSES` entry (`parse_device_config`) and
hands it to `build_hardware` — the same assembly path production demos use — to stand up
the **real assembled prop's outputs** (matrix + audio + optional motor + optional
IR/network controls), then loads one named scene against them, reporting the staged heap
it retains. `build_hardware` imposes a coarser boundary than the old per-driver setup
calls did, so the breakdown is one hardware-bundle delta followed by the stages the
profiler still owns individually:

- **`hardware` Δ** — the heap the single `build_hardware` call retains (matrix, audio,
  optional motor, optional IR/network controls, plus buttons/accelerometer it always
  wires but this profiler never reads).
- **`registries` Δ** — the heap scanning the effect/rule/scene `PackRegistry`s retains.
- **`engine` Δ** — the heap building `EffectManager` + `Timer` + `GameEngine` +
  `SceneManager` retains.
- **`load` Δ** — the heap `SceneManager.load(SCENE_NAME)` retains (the scene graph:
  phases, rules, effects).
- **first-tick Δ** — the heap the first `SceneManager.update()` retains (opening effects
  fire for the first time: palettes/LUTs/buffers built, WAV files opened).

Set `SCENE_NAME` to the scene you want and **confirm its `HARNESSES` entry matches the
prop you are running** — the registered audio clips, voice count, and IR wiring. The
harness is configured by hand, not derived from the scene; a recorded figure is valid
**only for the `(scene, harness)` pair it was measured against**. A harness with
`"ir": None` omits the `ir` key from the in-file config entirely, so `build_hardware`
wires no IR receiver and no network controls; `"tag"` / `"default"` pass the matching
wire-frame codec. A mismatched harness (missing clips or scopes) reproduces the
headless-style artifact that motivated dropping `scene_content`. Read the
`__SCENE_STAGES` line for the full staged free-heap breakdown and the
`__TABLE_ROW table=scene_in_situ_baselines` row (still just `load` Δ and first-tick Δ —
the two scene-specific figures) to paste into `recorded-metrics.md`. Run it once per
scene (`tag`, `red_light_green_light`, `hardware_test`), each on its matching harness —
these are standalone measurements, not additive terms.
