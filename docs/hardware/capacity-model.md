# Capacity Model

This document describes how the capacity estimator (`scripts/capacity/`) decides how a
prop's components are packed onto a board's MCUs, what each component costs, and the
measured constants it needs per `(board, runtime, driver)`.

The estimator is **CPU-only**: it does not model pixel bandwidth, render time inside an
effect, or anything outside the per-frame CPU and heap budgets described below.

> **Where things live.** This doc holds the model, the resource summary, and the
> measured constant tables. The *mechanics* of producing those constants on hardware
> (what each profiler sweeps and how to read its output) live in
> [`calibration-guide.md`](calibration-guide.md).

---

## Quick reference

### Component resource matrix

Every prop is built from these components. "Count" is how many a prop has;
"Splittable" is whether the packer may place it on its own MCU. Defaults are from
`scripts/capacity/profiles.py`.

| Component (`class`) | CPU cost shape | Heap footprint | I2C bus | Peripherals | Hard deadline? | Splittable? | Count per prop |
|---------------------|----------------|----------------|---------|-------------|----------------|-------------|----------------|
| Engine (`EngineComponent`) | `tick_fixed + per_rule·rules + per_event·events + router·remote_mcus` | static | — | — | no | no — anchors the engine-host | exactly 1 |
| Pixel scope (`PixelScopeComponent`) | `stack_depth · per_pixel · pixels + flush` | `base + per_pixel·pixels` | matrix driver only | — | no | **yes — per scope** | one per scope |
| Sound (`SoundComponent`) | `mixer_fixed + per_voice · voices` | static (by `num_voices`) | — | `i2s: 1` | no | no | 1 shared (`Scope.ALL`) |
| Vibration (`VibrationComponent`) | fixed per-event `cost_ms` | static | event-rate share | `i2c: 1` | no | no | 1 shared (`Scope.ALL`) |
| IR transmit (`IrTransmitComponent`) | near-zero avg `cost_ms` (+ `blocking_send_ms` soft-RT) | static | — | `pwm: 1` | no¹ | no | 1 shared |
| IR receive (`ReceiverComponent`) | fixed `cost_ms` | `base + per_slot · buffer_depth` | — | — | **yes (`max_frame_ms`)** | no | one per receiver |
| Accel / I2C poller (`SimpleComponent`) | fixed `cost_ms` | static | per-frame read | — | no | no | as wired |
| radio-tx (`SimpleComponent`, *uncalibrated*) | fixed `cost_ms` | static | — | — | no | no | 1 shared |
| radio-rx (`ReceiverComponent`, *uncalibrated*) | fixed `cost_ms` | `base + per_slot · depth` | — | — | **yes** | no | one per receiver |

¹ An `IrTransmitComponent` has no deadline of its own, but its `blocking_send_ms` is
added to the worst-case frame of any co-located receiver (see its cost model below).

### Board / FPS at a glance

- `target_fps` has a **24 FPS ceiling** and is the *ceiling*, not an achievable rate.
  The real rate is set by the single busiest MCU after baseline + headroom deductions.
- **Matrix `flush_ms` (~61 ms) alone exceeds the 24 FPS budget (41.7 ms)** — any
  IS31FL3741 scope caps the prop near **10–12 FPS** regardless of pixel count.
- **NeoPixel `per_pixel` (~0.55 ms/px)** makes long strips the binding term: ~60 px
  ≈ 19 FPS, ~144 px collapses to ~9 FPS.
- Logic-only MCUs (no pixel scope) stay CPU-cheap and hit the 24 FPS cap. Because pixel
  scopes split per-MCU, a multi-scope prop's ceiling is set by its single heaviest
  scope, not the sum.

See [Designing across processors](#designing-across-processors) for the worked tables.

---

## How packing works

### Frame budget and reservations

```
frame_budget_ms = 1000 / target_fps          (target_fps <= 24)
reserved%       = cost_ms / frame_budget_ms * 100
```

Each component's cost is a constant in milliseconds (`cost_ms`); the underlying
constant always stays in ms, only the *reservation* is expressed as a percentage.

### Per-MCU baseline

Before packing, each MCU's usable budget is reduced by a fixed baseline that depends on
its role:

- **engine-host**: runs the `GameEngine` tick loop. Exactly one per prop.
- **satellite**: a thin command executor with no rules.

```
usable_cpu%  = 100 - baseline_cpu_percent[role] - headroom_reserve_percent
usable_heap  = total_free_heap_bytes - baseline_heap_bytes[role] - gc_margin_bytes
```

`headroom_reserve_percent` defaults to 20% (tunable per board and per run).
`gc_margin_bytes` is heap held back on every MCU for CircuitPython's mark-sweep
collector — set generously (GC needs free space; fragmentation shrinks the usable
heap). It is configurable per board via `BoardProfile.gc_margin_bytes` (default `0`);
the engine baseline showed ~23 KB of GC churn, so ~23 KB is a reasonable setting on
this runtime.

### The assignment algorithm

The engine-host MCU is seeded with the engine component. Remaining components are
packed **first-fit-decreasing by CPU reservation** (largest first) onto the
engine-host, then onto satellite MCUs, opening a new satellite whenever a component
does not fit any existing MCU's CPU budget. Each `PixelScopeComponent` may be placed
independently (spread across satellites, or each on its own MCU); all other components
are indivisible.

`assign(prop, board, headroom_reserve_percent=None)` returns an `AssignmentResult`:

- **Feasible**: a list of MCUs, each with its role, the components placed on it (with
  `reserved%` and `uncalibrated` flag), its `remaining_headroom%`, and a
  `co_location_validated` flag.
- **Infeasible**: `feasible=False`, empty MCU list, and a `reason` naming the violated
  constraint.

### Constraints (in the order `assign()` checks them)

| Order | `conflict_type` | Check |
|-------|-----------------|-------|
| 1 | `deadline` | For each `ReceiverComponent`, `worst_case_frame_ms` (incl. any co-located IR-tx `blocking_send_ms`) must not exceed its derived `max_frame_ms`. **Pre-packing** — dominates the budget: even a workload that fits CPU/memory is rejected if it pushes the worst frame past the receiver's deadline. |
| 2 | `peripheral` | Summed `peripherals_required` across all components must not exceed `board.peripheral_budgets` (I2S/SPI/I2C/PWM). A peripheral with no budget entry is unconstrained. **Pre-packing.** |
| 3 | `cpu` | Per MCU, `sum(reserved%) <= usable_cpu%`. If a component's reservation exceeds a fresh satellite's usable CPU, the assignment is infeasible. |
| 4 | `memory` | Per MCU, `sum(memory_footprint_bytes) <= usable_heap`. Checked after CPU packing succeeds; names the offending MCU role. |
| 5 | `bus` | Summed `i2c_bandwidth_bytes_per_sec` across all pixel scopes, the `VibrationComponent`, and any I2C-polling `SimpleComponent` must not exceed the board's `"i2c"` bus budget. Checked after CPU and memory. |

---

## Component cost models

### Engine

```
cost_ms = tick_fixed_ms
        + per_rule_ms * rules
        + per_event_ms * events_per_tick
        + router_overhead_ms * remote_mcus
```

`router_overhead_ms` is a per-remote-MCU command/event overhead charged to the
engine's MCU — it scales with the number of remote MCUs the engine sends to, **not**
pixel bandwidth or strip length. (Still `_TBD_`; no in-tick seam to profile it yet.)

Two durable caveats:

- **Additive vs. product dispatch.** The real `GameEngine.update` loop dispatches every
  queued event to every rule (`O(events × rules)`), but the model is additive. The
  slopes are measured at a cross-load of 1; the additive estimate is a **lower bound**
  as both `rules` and `events` grow simultaneously.
- **`tick_fixed_ms` ↔ engine-host baseline overlap.** The `(0 rules, 0 events)` point
  is the same rule-less tick the engine-host `cpu_percent` baseline measures. Do **not**
  charge both in full — treat `tick_fixed_ms` as folded into the engine-host baseline
  and add only the marginal `per_rule_ms` / `per_event_ms` terms on top.

### Pixel scope

```
cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms
```

`stack_depth` is the max concurrent `add_effect` layers expected on the scope
(scene-declared; defaults to 1). Resolution is not a top-level axis — it is absorbed
into the profiled `worst_case_effect_per_pixel_ms`.

- **Per-scope splitting.** Each `PixelScopeComponent` may be placed independently — the
  packer can spread a prop's scopes across satellites, even one scope per MCU.
- **Driver dimension.** `driver` is `"neopixel_pwm"` or `"is31fl3741_matrix"`. It
  changes `worst_case_effect_per_pixel_ms`, `flush_ms`, and I2C usage
  (`i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * i2c_frequency_hz`). NeoPixel
  PWM is off the I2C bus (reports 0); the matrix flush is the dominant I2C consumer.
- **Router fan-out.** `estimator.fan_out_mcu_count(result, output_component_names)`
  returns the number of distinct remote MCUs hosting any named output. An effect
  command's router cost for a scope is `router_overhead_ms * fan_out_mcu_count(...)` —
  it fans out to every MCU hosting an output in the scope, not once per output.

### Sound

One shared I2S amp + `audiomixer.Mixer`; `AudioEffectOutput` is on `Scope.ALL`, so
exactly one `SoundComponent` serves every scope.

```
cost_ms = mixer_fixed_ms + per_voice_ms * effective_voices
effective_voices = min(max_concurrent_voices, num_voices)
```

`max_concurrent_voices` is the worst-case voices a scene stacks via `add_effect`,
**including audio-only effects** that hold a voice but render no pixels. `num_voices`
is `VoicePool`'s hard cap: stacking beyond it evicts the oldest voice, so
`effective_voices` (and `cost_ms`) is bounded.

### Vibration

One shared DRV2605L haptic motor over I2C (`Drv2605EffectOutput` on `Scope.ALL`).

```
cost_ms                      -- fixed per-event cost, declared directly
i2c_bandwidth_bytes_per_sec  = i2c_transaction_bytes * (max_calls_per_minute / 60)
```

`max_calls_per_minute` is low, so the average I2C share is negligible — but it is still
summed into the `"i2c"` bus budget alongside matrix-flush usage.

**LIS3DH accelerometer (I2C contribution).** An accelerometer read once per frame is
modeled as a `SimpleComponent` with `i2c_frequency_hz == target_fps`. Its
`i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * i2c_frequency_hz` is summed into
the `"i2c"` budget like any other I2C consumer.

### IR transmit

One shared transmit path: `HardwareNetworkControls.send_ir` selects 1 of up to 3 wired
emitters (LINE / CONE / AREA_OF_EFFECT) per send. Only one transmits at a time, so cost
does not scale with emitter count.

```
cost_ms           -- average per-frame CPU reservation (near zero)
blocking_send_ms  -- worst-case PulseOut.send blocking for the longest payload
```

`blocking_send_ms` is a **soft** real-time cost: `send_ir` blocks for the whole pulse
train, contributing to the worst-case frame of any co-located receiver. The deadline
check adds it to the receiver's `worst_case_frame_ms`:

```
receiver_worst_case_frame_ms = worst_case_frame_ms + blocking_send_ms
                               (if an IrTransmitComponent is present)
```

A prop with no `ReceiverComponent` has nothing for the blocking send to threaten, so an
`IrTransmitComponent` alone never triggers a deadline conflict.

`cost_ms` is the blocking duration amortized across the frames between sends:
`cost_ms = blocking_send_ms × send_rate_hz / target_fps`. At the realistic AURA cadence
(one 4-byte packet / 5 s → `send_rate_hz = 0.2`, `target_fps = 24`): ≈ 0.50 ms.

### IR receive (`ReceiverComponent`)

A hard-real-time receiver. `cost_ms` is the `fixed_drain` per-tick polling cost; the
correctness guard is a **deadline** checked against the worst-case single frame, not the
average:

```
max_frame_ms = buffer_depth / incoming_rate_hz * 1000
```

`max_frame_ms` is *derived* — the longest a frame can take before the buffer (e.g.
`PulseIn.maxlen`) overflows and data is dropped. If `worst_case_frame_ms > max_frame_ms`
the assignment is infeasible (`conflict_type="deadline"`), checked before CPU/memory. A
receiver with `incoming_rate_hz <= 0` has `max_frame_ms = None` and no deadline check.

**Buffer-depth trade-off (RAM for deadline).** `buffer_depth` is a single knob that
relaxes the deadline and raises memory together:

```
memory_footprint_bytes = base_footprint_bytes + bytes_per_buffer_slot * buffer_depth
```

Raising it to relieve a deadline can flip an otherwise-feasible assignment into a
memory conflict.

**IR-rx component.** `InfraredMultiReceiver` polling 4 `PulseInReader`s is modeled as a
single `ReceiverComponent`. The 4 readers are fixed (not a deployment axis): `cost_ms`
is the `fixed_drain` across all 4, plus the deadline above.

### Radio tx/rx (uncalibrated, #399)

Carried as **uncalibrated model entries** so the deployment math covers all 8
components, even though the radio transport seam and profilers are deferred to a
follow-on PRD (`send_radio` is a stub; no RFM69 driver; no receive seam yet).

- **radio-tx** — a `SimpleComponent` with a near-zero average `cost_ms` (like IR-tx).
- **radio-rx** — a `ReceiverComponent` reusing the IR-rx deadline model, with the
  radio's FIFO depth as `buffer_depth`.

Both set `uncalibrated=True`; `ComponentAssignment.uncalibrated` surfaces this per
component so reports distinguish profiler-measured from seed-constant placements.

RFM69HCW seed figures (datasheet, calibration deferred):

| Constant | Seed value | Source |
|----------|-----------|--------|
| FIFO depth (`buffer_depth`) | 66 bytes | RFM69HCW datasheet FIFO size |
| Incoming rate (`incoming_rate_hz`) | ~31,250 bytes/sec | 250 kbps GFSK air rate / 8 |
| Derived `max_frame_ms` (raw FIFO) | ~2.1 ms | `66 / 31250 * 1000` |

The raw-FIFO ~2.1 ms is a *tight* deadline. `FifoNotEmpty` / `FifoThreshold`
interrupt-driven streaming reads relax it by effectively raising the absorbable buffer
depth — the same buffer-depth-relief trade-off as IR-rx, left as a deployment knob.

---

## Designing across processors

### Achievable FPS from the busiest MCU

`target_fps = 24` is the ceiling; the real rate is set by the busiest MCU's worst-case
summed `cost_ms` after baseline + headroom. Inverting the packing inequality:

```
required_frame_budget_ms = Σ(cost_ms on busiest MCU) / usable_fraction
achievable_fps           = min(24, 1000 / required_frame_budget_ms)
```

`usable_fraction = (100 − baseline_cpu_percent − headroom_reserve_percent) / 100` —
i.e. **0.7435** on the engine-host (5.65% baseline) and **0.7479** on a satellite
(5.21%). Engine marginal cost here uses `per_rule_ms × rules + per_event_ms × events`
only (`tick_fixed_ms` is folded into the engine-host baseline; see the engine cost
model).

Worked from the `circuitpython_10_2_1` constants (each scope alone, `stack_depth = 1`):

| Representative busiest MCU | Σ cost_ms (worst frame) | required budget | achievable FPS |
|----------------------------|-------------------------|-----------------|----------------|
| Logic-only (engine 10 rules + 5 events, sound 4 voices, 1 haptic event) | ≈8.6 ms | 11.5 ms | **24** (capped) |
| NeoPixel PWM scope, 60 px | 0.552×60 + 5.84 = 38.96 ms | 52.1 ms | **≈19** |
| IS31FL3741 matrix scope, 100 px | 0.106×100 + 60.69 = 71.29 ms | 95.3 ms | **≈10** |
| IS31FL3741 matrix scope (flush floor, 0 px) | 60.69 ms | 81.1 ms | **≈12** |
| NeoPixel PWM scope, 144 px | 0.552×144 + 5.84 = 85.32 ms | 114.1 ms | **≈9** |

**Recommendation:** don't set a board-wide `target_fps` below 24; keep 24 as the
ceiling and choose the per-prop rate from the heaviest scope it deploys.

### Max pixels per MCU at a target FPS

While designing hardware (pixel count is an output, not a fixed input), invert the same
inequality:

```
max_pixels = (usable_fraction × frame_budget_ms − flush_ms) / (per_pixel_ms × stack_depth)
```

One scope alone on a satellite (`circuitpython_10_2_1`, `usable_fraction = 0.7479`,
`stack_depth = 1`):

| Target FPS | budget (ms) | NeoPixel max px (0.552/px, 5.84 flush) | Matrix max px (0.106/px, 60.69 flush) |
|-----------|-------------|----------------------------------------|----------------------------------------|
| 24 | 41.7 | **45** | infeasible (flush alone > budget) |
| 20 | 50.0 | **57** | infeasible |
| 15 | 66.7 | **79** | infeasible |
| 12 | 83.3 | **102** | ~15 |
| 10 | 100.0 | **124** | ~133 |

The crossover is the key design signal: the **matrix is unusable above ~12 FPS at any
size** (its 60.69 ms flush does not fit the budget), and only around **~10 FPS** does
its much cheaper per-pixel cost (0.106 vs 0.552 ms/px) let it match then overtake
NeoPixel's capacity. Driver choice and target FPS are one coupled decision; pixel count
falls out of it. Raising `stack_depth` divides `max_pixels` proportionally.

---

## Calibration data

Measured constants keyed by `(board, runtime, driver)`. See
[`calibration-guide.md`](calibration-guide.md) for how each table is produced and read.
Tables not yet populated carry `_TBD_` cells.

### Board profiles

Per-board frame budget and global heap/headroom budgets. `total_free_heap_bytes` is
profiler-measured (`baseline_profiler.py` "Mem Free"); `target_fps` (24 ceiling) and
`headroom_reserve_percent` (20% default) are config inputs. Source: `baseline_profiler.py`.

| Board | Runtime | Driver | `target_fps` | `total_free_heap_bytes` | `headroom_reserve_percent` |
|-------|---------|--------|--------------|-------------------------|------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 24 | 130576 | 20% |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 24 | 129536 | 20% |

### Per-MCU baselines

Fixed CPU and heap tax each role's bare framework loop consumes before any component
work. The `heap_bytes` is the **bare** framework (empty registry, no packs, no scene);
a real prop also loads a scene, which dominates its heap (see scene-content memory
below). Source: `baseline_profiler.py`.

| Board  | Runtime | Driver | Role | `cpu_percent` | `heap_bytes` |
|--------|---------|--------|------|---------------|--------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | engine-host | 4.75% | 656 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | satellite | 4.50% | 111 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | engine-host | 5.65% | 656 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | satellite | 5.21% | 464 |

### Engine component costs

Per-tick cost terms scaling with rules, events, and remote MCUs. Source:
`engine_profiler.py`.

| Board | Runtime | Driver | `tick_fixed_ms` | `per_rule_ms` | `per_event_ms` | `router_overhead_ms` |
|-------|---------|--------|------------------|----------------|-----------------|------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.0694 | 0.0621 | 0.1177 | _TBD_ |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.1728 | 0.0565 | 0.1147 | _TBD_ |

### Pixel scope costs

Per-frame render+flush terms, keyed by driver. `linear_fit` slope is
`worst_case_effect_per_pixel_ms`, intercept is `flush_ms`. Source: `pixel_profiler.py`.

| Board | Runtime | Driver | `worst_case_effect_per_pixel_ms` | `flush_ms` | `i2c_bandwidth_bytes_per_sec` |
|-------|---------|--------|----------------------------------|------------|-------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | neopixel_pwm | 0.523107 | 5.9815 | 0.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | is31fl3741_matrix | 0.103225 | 59.2329 | 8664.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | neopixel_pwm | 0.551999 | 5.8358 | 0.0 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | is31fl3741_matrix | 0.105998 | 60.6856 | 8664.0 |

### Pixel scope memory

Retained heap, keyed by driver. Predict a scope's footprint as
`base + per_pixel * pixel_count` (e.g. a 117-pixel matrix: `9607 + 2.80 * 117 ≈ 9935 B`).
Source: `pixel_profiler.py`.

| Board | Runtime | Driver | `footprint_base_bytes` | `footprint_per_pixel_bytes` |
|-------|---------|--------|------------------------|-----------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | neopixel_pwm | 8520 | 46.74 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | is31fl3741_matrix | 9607 | 2.80 |

The drivers split very differently. `neopixel_pwm` scales steeply (46.74 B/px — the
strip buffer grows per pixel). `is31fl3741_matrix` is nearly flat (2.80 B/px): the
buffered driver allocates a **fixed full-matrix (13×9) framebuffer off the GC heap** at
construction regardless of logical pixel count, so ~9.6 KB lands in
`footprint_base_bytes` and the slope reflects only the small per-row `PixelBuffer`s
(near measurement noise).

### Sound component costs

Per-frame mixer terms. `linear_fit` intercept is `mixer_fixed_ms`, slope is
`per_voice_ms`. Source: `sound_profiler.py`.

| Board | Runtime | Driver | `mixer_fixed_ms` | `per_voice_ms` |
|-------|---------|--------|------------------|----------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.1834 | 0.0521 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.1929 | 0.0425 |

### Sound component memory

Static idle footprint (`AudioEffectOutput`: I2SOut + `audiomixer.Mixer` + `VoicePool`),
keyed by `num_voices` (the reference `tag` prop uses 4). Source: `sound_profiler.py`.

| Board | Runtime | Driver | `num_voices` | `memory_footprint_bytes` |
|-------|---------|--------|--------------|--------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 4 | 4304 |

### Vibration component costs

Per-event cost for the shared DRV2605L. Source: `vibration_profiler.py`.

| Board | Runtime | Driver | `cost_ms` | `i2c_bandwidth_bytes_per_sec` |
|-------|---------|--------|-----------|-------------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 7.4870 | 1.80 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 7.0801 | 1.80 |

### Vibration component memory

Static footprint of the DRV2605L driver + `Drv2605EffectOutput` (a single value —
nothing scales). The shared I2C bus is excluded. Source: `vibration_profiler.py`.

| Board | Runtime | Driver | `memory_footprint_bytes` |
|-------|---------|--------|--------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 176 |

### IR-transmit component costs

`blocking_send_ms` here is the realistic 4-byte AURA payload. The worst-case across the
full payload sweep is ~757.81 ms — use that only for much longer payloads. Source:
`ir_tx_profiler.py`.

| Board | Runtime | Driver | `cost_ms` | `blocking_send_ms` |
|-------|---------|--------|-----------|--------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 0.50 | 59.81 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 0.50 | 59.57 |

### IR-transmit component memory

Static footprint of the transmitter path (LINE `PulseOut` + `InfraredTransmitter` +
`HardwareNetworkControls`); the receiver's `PulseIn` is excluded. Source:
`ir_tx_profiler.py`.

| Board | Runtime | Driver | `memory_footprint_bytes` |
|-------|---------|--------|--------------------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 192 |

### IR-receive component costs

Hard-real-time deadline, keyed additionally by `buffer_depth` and `incoming_rate_hz`.
`max_frame_ms` requires an external IR packet source (`_TBD_` on a bare board). Source:
`ir_rx_profiler.py`.

| Board | Runtime | Driver | `buffer_depth` | `incoming_rate_hz` | `max_frame_ms` |
|-------|---------|--------|----------------|--------------------|----------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_0_3 | - | 64 | 13.91 | 58.59 |
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 64 | 13.9 | 63.01 |

### IR-receive component memory

Retained footprint of one `ReceiverComponent`, sweeping `PulseIn.maxlen`. The
relationship is **non-linear**, so the `base + per_slot * buffer_depth` form does not
fit cleanly. Source: `ir_rx_profiler.py`.

| `PulseIn.maxlen` | measured footprint |
|------------------|--------------------|
| 64               | 752 B              |
| 256              | 672 B              |
| 1024             | 3488 B             |
| 2048             | 5536 B             |

At large depths the buffer scales at **~2.0 B/slot** (a `uint16` per slot; 1024→2048 is
exactly +2048 B), but small buffers quantize into a flat ~700 B baseline. The reference
`tag` prop's receiver is fixed at **maxlen = 256**, measured directly as **672 B** — use
that for reconciliation rather than extrapolating the non-linear fit (which would
over-predict at ~1088 B).

---

## Validation & known gaps

### Reference prop validation (#401)

The acceptance gate for the capacity PRD: confirm the calibrated estimator's prediction
matches reality for the reference prop — the **Adafruit RP2040 PropMaker Feather
running the `tag` scene** (IS31FL3741 matrix with all scopes composited on the one
matrix, I2S audio, DRV2605L vibration, one IR LINE emitter + one IR receiver, two
buttons, LIS3DH accelerometer — a single-MCU prop).

- **Prediction** — `python -m scripts.capacity.reference_props` runs the estimator
  against the calibrated `circuitpython_10_2_1` profile.
- **Measurement** — `tag_prop_profiler.py` stands up the assembled prop on hardware.

The matrix `flush_ms` (60.69 ms) busts the 24 FPS budget, so the prop is infeasible at
the ceiling; its achievable single-MCU rate is ~7.9 FPS. The comparison is taken at
**7 FPS** (the profiler's `TARGET_FPS`, so predicted and measured share a 142.9 ms
budget). Predicted figures are **amortized** (`amortized_engine_host_cost_ms`): the
packer reserves the full `VibrationComponent.cost_ms` (~7 ms) every frame for
feasibility, but the profiler reports *mean* busy time where the ≤6 calls/min haptic
amortizes to ~0.1 ms/frame — so the comparison amortizes it to match. All figures at
`num_voices = 4`. **Tolerance: ±5%** on CPU metrics; memory is excluded (all
`memory_footprint_bytes` still uncalibrated).

| Metric | Predicted (amortized, 7 FPS) | Measured | Relative Δ | Within ±5%? |
|--------|------------------------------|----------|------------|-------------|
| CPU reservation | 60.92% | 60.41% | +0.8% | ✅ |
| Headroom | 13.43% | 13.94% | −3.7% | ✅ |
| Worst-case frame | 146.6 ms | 150.88 ms | −2.8% | ✅ |
| Memory footprint | ~0 (uncalibrated) | 32,608 B | n/a (excluded) | — |

Measured row (`circuitpython_10_2_1`, `tag_prop_profiler.py`):

| Board | Runtime | Driver | reservation% | footprint_B | headroom% | peak_frame_ms |
|-------|---------|--------|--------------|-------------|-----------|---------------|
| adafruit_feather_rp2040_prop_maker | circuitpython_10_2_1 | - | 60.41% | 32608 | 13.94% | 150.8789 |

**Result: PASS.** All three CPU metrics fall within ±5%. Reservation and headroom err in
the safe direction (the model over-predicts cost). The worst-case frame is
under-predicted by 2.8% (the unsafe side, within tolerance); the swing is dominated by
`frame_time_peak` run-to-run noise (whether a blocking IR send coincides with GC on the
single worst frame), not voice count. If the worst-frame margin matters, characterise
the peak across several runs rather than one. The pre-correction predictions were
uniformly ~8.8% high; amortizing vibration over its duty cycle for the comparison (a
comparison-only adjustment in `reference_props.py`, leaving the packer's worst-case
reservation untouched) brought all metrics to ≤3.9%.

**Follow-up (open).** Calibrate component `memory_footprint_bytes` (all `_TBD_`): the
predicted memory footprint is ~0 against a measured 32,608 B, so memory cannot yet be
validated against tolerance.

### Assembled-prop memory breakdown (#448)

The bare baseline (656 B) excludes scanned packs and the loaded scene. The reference
`tag` prop's measured ~32.8 KB decomposes via `tag_prop_profiler.py`'s
`__PROP_BREAKDOWN` (staged `gc.mem_free()` deltas):

| Stage | Bytes | What it is |
|-------|-------|------------|
| peripherals | 6,624 | matrix/buttons/accel/motor/IR hardware drivers + shared I2C bus |
| registries | 1,328 | scanned effect + rule pack registries (factory callables) |
| audio_outputs | 5,632 | audio registry+output, `EffectOutput` wrappers, `EffectManager` |
| engine | 160 | Timer + GameEngine + HardwareNetworkControls |
| **scene** | **19,088** | **scene load + first tick (see below)** |
| **total** | **32,832** | matches the measured assembled footprint |

This is the only decomposition that sums to the measured total; it is a measurement of
*this* prop, not a portable predictive model.

#### Scene-content memory: a model gap, not a calibratable term (#448)

The `scene` stage (~58% of the heap) was investigated with `baseline_profiler.py`
`MODE = "scene_content"` (finer `__SCENE_STAGES` snapshots + a `BALLAST_BYTES`
free-heap test). Findings:

- **It is entirely the first tick.** `manager.load()` allocates ~80 B (just queues the
  transition); `manager.update()` -- which instantiates the active phase and **adds its
  effects** -- allocates the rest. So this is *dynamic first-tick effect allocation*, not
  a static scene graph.
- **It is output-coupled, and headless over-measures it ~2x.** Loaded headless (a
  `NullEffectOutput`), the first tick allocates ~30-33 KB vs. ~15.5 KB in-situ. Against
  the real matrix the buffered IS31FL3741 driver keeps pixels in a **native framebuffer
  (off the GC heap)** -- which is why the matrix per-slot footprint measured ~0 -- so
  the effects' pixel data lives off-heap; headless it falls back onto the GC heap.
- **It is not allocation context.** Shrinking the free heap by 50 KB of ballast (to the
  in-situ ~71 KB at load) moved the figure only ~3 KB, ruling out free-heap-dependent
  GC retention.

**Conclusion:** scene/effect memory cannot be captured as a portable additive term -- it
is dynamic and output-coupled, so a headless measurement is an artifact (~2x), and the
in-situ `scene` stage (~19 KB) is only measurable on the assembled prop. The capacity
model's per-component footprints therefore **do not sum to the assembled total**, and a
predicted-vs-measured memory validation to a tight tolerance is not achievable with the
current model. Tracked as #450 (an output-coupled scene/effect memory model).
