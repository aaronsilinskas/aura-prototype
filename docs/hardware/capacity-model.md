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
`i2c_bandwidth_bytes_per_sec` across all of a prop's pixel scopes is checked against
the board's `"i2c"` bus budget. If it exceeds the budget, the assignment is infeasible
with `conflict_type="bus"`, even if CPU and memory both have room. Switching an
over-budget scope's driver to NeoPixel PWM removes its I2C load entirely.

### Router fan-out

`estimator.fan_out_mcu_count(result, output_component_names)` returns the number of
distinct remote (non-engine-host) MCUs hosting any of the named output components.
An effect command's router cost for a scope is
`router_overhead_ms * fan_out_mcu_count(result, scope_output_names)` -- it fans out to
every MCU hosting an output in the scope, not once per output.

## Assignment output

`assign(prop, board, headroom_reserve_percent=None)` returns an `AssignmentResult`:

- **Feasible**: a list of MCUs, each with its role (`engine-host` / `satellite`), the
  components placed on it with their `reserved%`, the MCU's `remaining_headroom%`,
  and a `co_location_validated` flag.
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
| _TBD_ | _TBD_   | _TBD_  | _TBD_            | _TBD_          | _TBD_           | _TBD_                  |
