# Capacity Model

This document describes the formulas used by the capacity estimator
(`scripts/capacity/`) to decide how a prop's components are packed onto a board's
MCUs, and tracks the constants the estimator needs per `(board, runtime, driver)`.

The estimator is CPU-only: it does not model pixel bandwidth, render time inside an
effect, or anything outside the per-frame CPU and heap budgets described below.

## Frame budget

```
frame_budget_ms = 1000 / target_fps
```

`target_fps` is a tunable target tick rate per board, with a 24 FPS ceiling (i.e.
`target_fps <= 24`).

## Reservation model

Every component's cost is defined as a constant in milliseconds (`cost_ms`) and
converted to a percentage of the frame budget:

```
reserved% = cost_ms / frame_budget_ms * 100
```

The underlying constant always stays in milliseconds; only the *reservation* is
expressed as a percentage.

## Per-MCU baseline deduction

Before packing, each MCU's usable budget is reduced by a fixed baseline that depends
on its role:

- **engine-host**: runs the `GameEngine` tick loop. Exactly one per prop.
- **satellite**: a thin command executor with no rules.

```
usable_cpu%  = 100 - baseline_cpu_percent[role] - headroom_reserve_percent
usable_heap  = total_free_heap_bytes - baseline_heap_bytes[role] - gc_margin_bytes
```

`headroom_reserve_percent` defaults to 20% and is tunable per board (and per
assignment run). `gc_margin_bytes` defaults to 0 and is configurable per board (see
"Memory constraint" below).

## CPU and memory bin-packing

Components are packed onto the fewest MCUs such that, for every MCU:

```
sum(reserved% for components on this MCU)            <= usable_cpu%
sum(memory_footprint_bytes for components on this MCU) <= usable_heap
```

The engine-host MCU is seeded with the engine component; remaining components are
packed first-fit-decreasing by CPU reservation (largest reservation first) onto the
engine-host, then onto satellite MCUs, opening a new satellite whenever a component
does not fit on any existing MCU's CPU budget.

If a component's reservation exceeds the usable CPU budget of a fresh satellite MCU,
the assignment is infeasible and the result names the offending component and the
violated constraint (`conflict_type="cpu"`).

After CPU packing succeeds, each MCU's summed memory footprint is checked against its
`usable_heap`. If any MCU overflows, the assignment is infeasible with
`conflict_type="memory"`, naming the offending MCU role and the violated heap budget.

## Memory constraint

Every component declares a static `memory_footprint_bytes`: its steady-state heap
usage, profiler-measured via a `mem_free` delta (placeholder/synthetic constants until
calibrated against real hardware).

`gc_margin_bytes` is a fixed amount of heap held back on every MCU of a board, on top
of the role's `heap_bytes` baseline, to leave room for CircuitPython's mark-sweep
collector. It should be set generously: GC needs free space to operate, and
fragmentation shrinks the heap that is actually usable for allocations. It is
configurable per board via `BoardProfile.gc_margin_bytes` (default `0`).

### Receiver buffer depth (RAM-for-deadline trade-off)

A hard-real-time receiver component (`ReceiverComponent`) has a tunable
`buffer_depth` -- e.g. the depth of an IR pulse buffer or a radio FIFO. Raising
`buffer_depth` relieves the receiver's polling deadline (it can tolerate longer gaps
between polls before overflowing) but increases its memory footprint:

```
memory_footprint_bytes = base_footprint_bytes + bytes_per_buffer_slot * buffer_depth
```

This makes the RAM-for-deadline trade-off visible to the estimator: raising
`buffer_depth` to relieve a deadline can flip an otherwise-feasible assignment into a
memory conflict.

## Hard-real-time deadline constraint

`ReceiverComponent` introduces a correctness guard that average CPU reservation
percentages cannot provide: a hard-real-time **deadline**. Unlike `cost_ms` (a
per-frame *average* CPU cost), the deadline is checked against the **worst-case**
single frame.

```
max_frame_ms = buffer_depth / incoming_rate_hz * 1000
```

`max_frame_ms` is *derived*, not declared: it is the longest a frame can take before
the receiver's buffer (e.g. `PulseIn.maxlen`) overflows and pulses are dropped. It is
the same `buffer_depth` used by the memory footprint above -- raising `buffer_depth`
both relaxes the deadline (raises `max_frame_ms`) and increases
`memory_footprint_bytes`, making the RAM-for-deadline trade-off a single knob.

`worst_case_frame_ms` is the worst-case single frame time measured on the receiver's
MCU (profiler-measured via `PerformanceTracker.frame_time_peak`, in milliseconds --
see the IR-rx profiler below).

**The deadline dominates the budget**: if `worst_case_frame_ms > max_frame_ms`, the
assignment is infeasible with `conflict_type="deadline"`, checked *before* CPU/memory
packing -- even a co-located workload that would otherwise fit comfortably within the
CPU reservation budget is rejected once it pushes the worst-case frame past the
receiver's deadline. A receiver with `incoming_rate_hz <= 0` (not yet profiled for
incoming rate) has `max_frame_ms = None` and no deadline is checked.

### IR-rx component

The IR-receive component (`InfraredMultiReceiver` polling 4 `PulseInReader`s) is
modeled as a single `ReceiverComponent`. The 4 receivers are **fixed, not a
deployment axis** -- `cost_ms` is the `fixed_drain` per-tick polling cost across all
4 readers, plus the deadline described above.

### IR-rx profiler

`examples/hardware/profiling/ir_rx_profiler.py` drives `InfraredMultiReceiver.receive()`
polling the fixed 4 `PulseInReader`s, using the **tunable-injected-load technique**:
an artificial per-frame busy-loop (`INJECTED_LOAD_MS`) is swept upward
(`INJECTED_LOAD_SWEEP_MS`) to simulate co-located CPU load. A known incoming packet
rate is induced via loopback from an IR transmitter or a second board; the profiler
counts sequence-number gaps to compute a packet-loss rate. The injected load at which
packet loss first becomes non-zero empirically locates `max_frame_ms` for the
profiled `BUFFER_DEPTH` (`PulseIn.maxlen`) and `INCOMING_RATE_HZ`. The profiler
reports packet-loss rate vs. injected frame time alongside the uniform
`PerformanceTracker` stats line (including `frame_time_peak`, the `worst_case_frame_ms`
term).

## Engine component cost model

```
cost_ms = tick_fixed_ms
        + per_rule_ms * rules
        + per_event_ms * events_per_tick
        + router_overhead_ms * remote_mcus
```

`router_overhead_ms` is a per-remote-MCU command/event overhead charged to the
engine's MCU. It scales with the number of remote MCUs the engine sends
commands/events to -- it is **not** based on pixel bandwidth or strip length.

## Pixel scope cost model

A `PixelScopeComponent` represents one pixel scope's per-frame render+flush cost:

```
cost_ms = stack_depth * worst_case_effect_per_pixel_ms * pixel_count + flush_ms
```

`stack_depth` is the maximum number of concurrent `add_effect` layers expected on the
scope (a scene-declared workload parameter); it defaults to 1. Resolution is not a
top-level axis here -- it only affects flame/drift-noise update internally and is
absorbed into the profiled `worst_case_effect_per_pixel_ms`.

### Per-scope splitting

Unlike `EngineComponent`, `SimpleComponent`, and `ReceiverComponent` (always packed as
a single indivisible unit), each `PixelScopeComponent` in a prop's `components` list
may be placed independently -- the packer can spread a prop's pixel scopes across
multiple satellite MCUs, including placing each scope on its own MCU in the extreme
case. The engine component and other indivisible components never split.

### Driver dimension

`driver` is one of `"neopixel_pwm"` or `"is31fl3741_matrix"`. The driver changes:

- `worst_case_effect_per_pixel_ms` and `flush_ms` (both per-`(board, runtime, driver)`
  constants)
- I2C bus usage: `i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * i2c_frequency_hz`.
  NeoPixel PWM is off the I2C bus and reports 0; the IS31FL3741 matrix flush is the
  dominant I2C consumer.

### Bus-bandwidth constraint

Each shared bus (I2C/SPI/I2S) declared in `BoardProfile.bus_budgets` has a
`bandwidth_bytes_per_sec` budget. After CPU and memory packing succeed, the summed
`i2c_bandwidth_bytes_per_sec` across all of a prop's pixel scopes **and its
`VibrationComponent`** (the DRV2605L's event-rate contribution) is checked against
the board's `"i2c"` bus budget. If it exceeds the budget, the assignment is infeasible
with `conflict_type="bus"`, even if CPU and memory both have room. Switching an
over-budget scope's driver to NeoPixel PWM removes its I2C load entirely.

### Router fan-out

`estimator.fan_out_mcu_count(result, output_component_names)` returns the number of
distinct remote (non-engine-host) MCUs hosting any of the named output components.
An effect command's router cost for a scope is
`router_overhead_ms * fan_out_mcu_count(result, scope_output_names)` -- it fans out to
every MCU hosting an output in the scope, not once per output.

## Sound component cost model

`SoundComponent` represents the single shared sound output: one I2S amp + one
`audiomixer.Mixer`. ``AudioEffectOutput`` is registered on `Scope.ALL`, so exactly one
`SoundComponent` serves every scope.

```
cost_ms = mixer_fixed_ms + per_voice_ms * effective_voices
effective_voices = min(max_concurrent_voices, num_voices)
```

`max_concurrent_voices` is the worst-case number of voices a scene can stack via
`add_effect`, **including audio-only effects** that hold a voice but render no pixels
(an effect whose `pixels` and `vibration` are both `None`, per
`AudioEffectOutput.handle_event`'s `audio_only` check -- such an effect still claims a
`VoicePool` slot). `num_voices` is `VoicePool`'s hard cap: a scene that would stack
more concurrent voices than `num_voices` simply evicts the oldest voice (see
`VoicePool._select_slot`), so `effective_voices` never exceeds `num_voices` and
`cost_ms` is bounded.

## Vibration component cost model

`VibrationComponent` represents the single shared haptic motor: a DRV2605L driven
over I2C via `Drv2605EffectOutput`, registered on `Scope.ALL`.

```
cost_ms  -- a fixed per-event cost, declared directly (not a formula)
i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * (max_calls_per_minute / 60)
```

`max_calls_per_minute` bounds how often `handle_event` writes a new sequence and
calls `motor.play()` -- a low rate, so the DRV2605L's average I2C bus share is
negligible but still summed into the board's `"i2c"` bus budget alongside any pixel
scope's matrix-flush usage (see "Bus-bandwidth constraint" below).

### LIS3DH accelerometer (I2C bus contribution)

A LIS3DH accelerometer read once per frame (e.g. for `AccelerationData` in
`engine/input.py`) is modeled as a `SimpleComponent` with `i2c_transaction_bytes` and
`i2c_frequency_hz` set (`i2c_frequency_hz` == the board's `target_fps`, since it is
read once per tick):

```
i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes * i2c_frequency_hz
```

`SimpleComponent`'s I2C fields default to 0 for components off the I2C bus. Any
`SimpleComponent` with nonzero `i2c_bandwidth_bytes_per_sec` is summed into the
board's `"i2c"` bus budget alongside pixel-scope and vibration I2C usage.

## IR-transmit component cost model

`IrTransmitComponent` represents the single shared IR-transmit path:
`HardwareNetworkControls.send_ir` selects 1 of up to 3 wired
`InfraredTransmitter` instances (LINE / CONE / AREA_OF_EFFECT) per send. The emitters
add no parallel cost -- only one transmits at a time, so the cost model does not scale
with how many emitter pins are wired.

```
cost_ms            -- average per-frame CPU reservation (typically near zero)
blocking_send_ms   -- worst-case PulseOut.send blocking duration for the longest
                      payload this prop transmits
```

`blocking_send_ms` is a *soft* real-time cost: `send_ir` blocks for the whole pulse
train, so it contributes to the worst-case frame time of any co-located
`ReceiverComponent` -- the receiver's buffer must absorb the gap while the
transmitter blocks. The deadline check adds `blocking_send_ms` to
`worst_case_frame_ms` before comparing against `max_frame_ms`:

```
receiver_worst_case_frame_ms = worst_case_frame_ms + blocking_send_ms (if an
                                IrTransmitComponent is present in the prop)
```

A prop with no `ReceiverComponent` has nothing for the blocking send to threaten, so
`IrTransmitComponent` alone never triggers a deadline conflict.

## Radio tx/rx components (uncalibrated, #399)

The radio transmitter and radio receiver are carried in the estimator as
**uncalibrated model entries** so the deployment math covers all 8 components, even
though the radio transport seam and its profilers are deferred to a follow-on PRD --
`send_radio` is currently a stub, there is no RFM69 driver, and no receive seam exists.

- **radio-tx** is modeled as a `SimpleComponent` (a near-zero average `cost_ms`,
  analogous to `IrTransmitComponent`'s average cost).
- **radio-rx** is modeled as a `ReceiverComponent`, reusing the hard-real-time
  deadline model from IR-rx (#397): `max_frame_ms = buffer_depth / incoming_rate_hz *
  1000`, with the radio's FIFO depth as `buffer_depth`.

Both entries set `uncalibrated=True`. Assignment output (`ComponentAssignment.uncalibrated`)
surfaces this flag per component, so reports can distinguish components placed using
real profiler measurements from components placed using documented seed constants.

### RFM69HCW seed figures (datasheet, calibration deferred)

The following constants are seeded from the RFM69HCW datasheet, not profiler
measurements. They will be replaced once a real radio seam and profiler exist
(follow-on PRD):

| Constant | Seed value | Source |
|----------|-----------|--------|
| FIFO depth (`buffer_depth`) | 66 bytes | RFM69HCW datasheet FIFO size |
| Incoming rate (`incoming_rate_hz`) | ~31,250 bytes/sec | 250 kbps GFSK air rate / 8 |
| Derived `max_frame_ms` (raw FIFO) | ~2.1 ms | `66 / 31250 * 1000` |

The raw-FIFO `max_frame_ms` (~2.1ms) is a *tight* deadline -- reading the FIFO only
once it is completely full leaves almost no slack. `FifoNotEmpty` / `FifoThreshold`
interrupt-driven streaming reads (draining the FIFO as bytes arrive, rather than
waiting for it to fill) relax this ceiling by effectively raising the buffer depth
the estimator can absorb before overflow -- this is the same buffer-depth-relief
trade-off described above for IR-rx, and is left as a deployment knob.

Calibration of these constants against real RFM69HCW hardware (`worst_case_frame_ms`
via `PerformanceTracker`, actual `cost_ms`, and `memory_footprint_bytes`) and a
real receive seam are deferred to a follow-on PRD.

## Peripheral-count constraint

Each board declares a finite count of shared peripheral types (I2S/SPI/I2C/PWM) via
`BoardProfile.peripheral_budgets: dict[str, PeripheralBudget]`. Each component
declares how many units of a peripheral it requires via
`peripherals_required: dict[str, int]` (e.g. `SoundComponent` defaults to
`{"i2s": 1}`, `VibrationComponent` to `{"i2c": 1}`, `IrTransmitComponent` to
`{"pwm": 1}`).

The summed `peripherals_required` across all of a prop's components is checked
against `board.peripheral_budgets`, **before CPU/memory packing** -- alongside the
hard-real-time deadline check. If any peripheral's total requirement exceeds its
budget, the assignment is infeasible with `conflict_type="peripheral"`, naming the
peripheral, the required count, and the available count (e.g. two components both
requiring the single I2S is reported as a peripheral conflict even if CPU and memory
both have ample room). A peripheral with no entry in `peripheral_budgets` is treated
as unconstrained.

## Assignment output

`assign(prop, board, headroom_reserve_percent=None)` returns an `AssignmentResult`:

- **Feasible**: a list of MCUs, each with its role (`engine-host` / `satellite`), the
  components placed on it with their `reserved%` and `uncalibrated` flag, the MCU's
  `remaining_headroom%`, and a `co_location_validated` flag.
- **Infeasible**: `feasible=False`, an empty MCU list, and a `reason` string naming
  the violated constraint (e.g. which component exceeded which budget).

## Constants tables

Constants are keyed by `(board, runtime, driver)`. These tables are currently empty
placeholders -- they will be populated as real hardware measurements become
available (see #392).

### Board profiles

| Board | Runtime | Driver | `target_fps` | `total_free_heap_bytes` | `headroom_reserve_percent` |
|-------|---------|--------|--------------|-------------------------|------------------------------|
| _TBD_ | _TBD_   | _TBD_  | _TBD_        | _TBD_                   | _TBD_                         |

### Per-MCU baselines

| Board | Runtime | Driver | Role | `cpu_percent` | `heap_bytes` |
|-------|---------|--------|------|---------------|--------------|
| _TBD_ | _TBD_   | _TBD_  | engine-host | _TBD_ | _TBD_ |
| _TBD_ | _TBD_   | _TBD_  | satellite   | _TBD_ | _TBD_ |

### Engine component costs

| Board | Runtime | Driver | `tick_fixed_ms` | `per_rule_ms` | `per_event_ms` | `router_overhead_ms` |
|-------|---------|--------|------------------|----------------|-----------------|------------------------|
| _TBD_ | _TBD_   | _TBD_  | _TBD_            | _TBD_          | _TBD_           | _TBD_ (#409, see note) |

#### Reading the profiler output (`engine_profiler.py`, #409)

`examples/hardware/profiling/engine_profiler.py` drives the real
`GameEngine.update(state)` dispatch loop with a synthetic `_ProfilerRule` /
`_ProfilerEvent` pair and reports per-tick Update Time via the uniform stats
line, sweeping `rule_count` and `events_per_tick` as independent axes (each
holding the other at a fixed reference of 1):

- **`tick_fixed_ms`** -- read directly from the `(rule_count=0,
  events_per_tick=0)` point's average Update Time. This is the fixed cost of
  one `GameEngine.update` tick with no rules and no queued events.
- **`per_rule_ms`** -- the slope of average Update Time vs `rule_count`, with
  `events_per_tick` held at 1. Computed as `(update_time(rules) -
  update_time(rules=0, events=1)) / rules` across the `RULE_COUNTS` sweep.
- **`per_event_ms`** -- the slope of average Update Time vs `events_per_tick`,
  with `rule_count` held at 1. Computed as `(update_time(events) -
  update_time(rules=1, events=0)) / events` across the `EVENTS_PER_TICK_VALUES`
  sweep.

**Additive model vs. real dispatch shape.** The estimator models per-tick
engine cost additively as `tick_fixed_ms + per_rule_ms * rules + per_event_ms *
events`, but the real `GameEngine.update` dispatch loop is product-shaped: every
queued event is dispatched to every registered rule (`O(events x rules)`
`handle_event` calls), not `O(events + rules)`. The additive model is an
approximation; `per_rule_ms` and `per_event_ms` are slopes measured at the
sweep's reference cross-load (1 event when sweeping rules, 1 rule when sweeping
events), not pure marginal costs at all cross-loads. At small reference values
(1) the product and sum shapes are close, but the approximation degrades as
both `rules` and `events` grow simultaneously -- callers with large props
(many rules and many events per tick) should treat the additive estimate as a
lower bound.

**`tick_fixed_ms` <-> engine-host baseline overlap.** The `(rule_count=0,
events_per_tick=0)` point profiled here calls the exact same rule-less
`GameEngine.update(state)` as `baseline_profiler.py`'s `engine_host` mode,
whose `cpu_percent` is recorded in the Per-MCU baselines table above. The two
measurements cover the same cost: the fixed per-tick engine overhead with zero
rules and zero events. The estimator must not charge both the engine-host
`cpu_percent` baseline *and* `tick_fixed_ms` for the same prop -- either treat
`tick_fixed_ms` as already included in the engine-host baseline (and add only
the marginal `per_rule_ms` / `per_event_ms` terms on top of it), or treat the
engine-host baseline's non-engine portion (framework loop, effect manager tick)
as the baseline and add the full `tick_fixed_ms` + marginal terms -- but not
both in full.

**`router_overhead_ms`** is out of scope for this profiler: it is the cost of
shipping commands from the engine host to remote satellite MCUs, which has no
seam inside the `GameEngine.update` tick loop measured here. The table cell
remains `_TBD_` pending a separate counting network stub or analytic seeding
(no tracking issue yet -- to be filed as a follow-up).
