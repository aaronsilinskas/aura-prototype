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
usable_heap  = total_free_heap_bytes - baseline_heap_bytes[role]
```

`headroom_reserve_percent` defaults to 20% and is tunable per board (and per
assignment run).

## CPU-only bin-packing

Components are packed onto the fewest MCUs such that, for every MCU:

```
sum(reserved% for components on this MCU) <= usable_cpu%
```

The engine-host MCU is seeded with the engine component; remaining components are
packed first-fit-decreasing (largest reservation first) onto the engine-host, then
onto satellite MCUs, opening a new satellite whenever a component does not fit on any
existing MCU.

If a component's reservation exceeds the usable budget of a fresh satellite MCU, the
assignment is infeasible and the result names the offending component and the
violated constraint.

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
