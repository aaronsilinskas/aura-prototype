# Context: aura-prototype

## Glossary

### GameRule
An event handler registered with `GameEngine`. **Stateless** — a rule instance must not accumulate mutable game data as instance attributes. All data that changes over the life of a game (scores, durations, counters, health, inventory) must live in `GameState.data`. Construction-time configuration injected via `__init__` (event maps, callbacks) is the only permitted use of instance attributes.

### GameState
The persistent game context owned by `GameEngine`. Passed by reference to every rule handler on every tick. Exposes `effect_controls`, `data`, read-only `elapsed`/`total` time properties, and a `queue_event(event)` method. Rules have no reference to `GameEngine` — `queue_event` is the only engine operation available inside a rule handler. The `data` dict is the canonical store for all mutable game data shared across rules. Rules must not write to `elapsed` or `total`.

### Timer
Owned internally by `GameEngine`. Tracks elapsed time per tick and cumulative total. Rules never hold a `Timer` reference — they access time only via `state.elapsed` and `state.total`. An optional `Timer` can be injected into `GameEngine` at construction for test-time clock control.
