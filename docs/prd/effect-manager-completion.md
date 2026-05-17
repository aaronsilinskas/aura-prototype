# PRD: EffectManager Completion

## Problem Statement

`EffectManager` exists as a public API with a well-designed interface but a hollow implementation. Callers can invoke `set_effect`, `add_effect`, and `update` without error, but no pixels are ever rendered to hardware, no events reach outputs, and no element renderer is ever built from the registry. The class is silently broken — it stores data correctly but produces no observable behavior.

The current code was written as an exploration and prototype. The design direction is sound; what is missing is a working implementation, tests that specify the expected behavior, and documentation that reflects reality.

## Solution

Complete `EffectManager` using TDD with vertical slices. Each slice adds one observable behavior, verified by a test written first. The implementation proceeds in the narrowest vertical cut possible — one test, one behavior — rather than filling in all TODOs at once.

The result is a manager where:
- Passing outputs at construction and setting an effect causes pixels to be rendered to those outputs on each `update` call
- Events triggered by an effect renderer (e.g. `"lightning_strike"`) are forwarded to every output in scope
- Resolution for a new effect is negotiated from the registered outputs that match its scope
- Setting an effect replaces any existing effect in scope; adding layers alongside it
- Stopping an effect removes it from all matching scope keys

## User Stories

1. As a developer, I want to call `manager.set_effect(Scope.PERSONAL, "fire", level=5, options={})` and have fire rendered to the personal output each frame, so that I don't need to wire up EffectRenderer, EffectState, and PixelBuffer myself.
2. As a developer, I want `set_effect` to replace any currently running effect in the scope, so that switching spells does not layer indefinitely.
3. As a developer, I want `add_effect` to layer a new effect alongside an existing one in scope, so that multi-element spells can run concurrently.
4. As a developer, I want `stop_effect` to remove all effects from a scope and stop pixel output for that scope, so that a scope goes dark when a spell ends.
5. As a developer, I want to pass a plain `list[EffectOutput]` at construction time, where each output carries its own `min_resolution` and `scopes`, so that the call site is clean and the output set is fixed before any effect is set.
6. As a developer, I want resolution to be negotiated from the outputs that match a scope, so that the element builder always receives the correct pixel count without the caller specifying it.
7. As a developer, I want events from an effect (e.g. `"lightning_strike"`) to be forwarded to every `EffectOutput` in the matching scope, so that audio and haptic drivers respond to visual effects without extra wiring.
8. As a developer, I want `update(timer)` to advance all unique renderers exactly once per frame and push a rendered `PixelBuffer` to every matching output, so that the caller drives everything with a single tick.
9. As a developer, I want an output whose scopes do not match the active effect's scope to receive no frames, so that scope routing is enforced and outputs only see effects intended for them.
10. As a developer, I want `Scope.ALL` to address every registered output, so that a "stop all effects" call clears everything without enumerating scopes.
11. As a developer, I want effects in overlapping scopes (e.g. `Scope.PERSONAL` and `Scope.ALL`) to be rendered correctly without double-updating a shared renderer, so that the existing de-duplication by renderer identity is preserved.
12. As a developer, I want `EffectManager` to require an `EffectBuilder` at construction, so that the active effect set is always an explicit choice determined by the running game rather than an implicit default.
13. As a developer, I want to compose multiple effect packs into a single `EffectBuilder`, so that different modules (elements, spells, UI) can each register their own effects without coupling to each other.

## Implementation Decisions

### Modules to build or modify

**`EffectManager`** — complete the hollow implementation. The public interface (`set_effect`, `add_effect`, `stop_effect`, `update`) is already correct. `register_output` is removed — outputs are supplied at construction as a plain `list[EffectOutput]`, each carrying its own `min_resolution` and `scopes`, and are fixed for the lifetime of the manager. The work is inside:

- `__init__`: accept `builder: EffectBuilder` and `outputs: list` (each entry an `EffectOutput`). Store both. Add `"_builder"` and `"_outputs"` to `__slots__`.
- `_build_effect`: resolve resolution from `_outputs` entries whose scopes overlap the given scope, construct `RendererConfig`, call the `EffectBuilder`, return a `(EffectRenderer, EffectState)` pair. If the builder raises for an unknown name, propagate the exception directly — no wrapping, no recovery.
- `update`: two explicit passes. **Pass 1 (advance)**: iterate `_effects.values()`, advance each unique renderer once via `_seen` de-dup (existing logic). **Pass 2 (render)**: for each output in `_outputs`, clear `_seen` and pre-gather unique `(renderer, state)` pairs whose scope key appears in the output's matched keys (de-dup by `id(renderer)` reusing `_seen`), then render each pair into a buffer via `output.create_buffer()` + `renderer.render(state, buf)`, collect into `frames`, and call `output.update_pixels(frames)`. Always call `update_pixels`, even with an empty list — `update_pixels([])` is the signal to the output to go dark.
- `_notify_listeners`: iterate `_outputs` whose scopes intersect the given scope and call `output.handle_event(event_name)`.

**`EffectBuilder` (protocol/base)** — already defined. Required at construction time — no default:

```python
manager = EffectManager(builder=some_pack, outputs=[led_strip, haptic_motor])
```

**`add_effect` on an empty scope** — valid; behaves identically to `set_effect`. No prior effect is required.

**`stop_effect` scope semantics** — clears exactly the keys in the given scope. If an effect was set with `Scope.ALL` and you call `stop_effect(Scope.PERSONAL)`, only the `"personal"` key is cleared; the effect continues in all other keys. To fully stop an effect set at `Scope.ALL`, call `stop_effect(Scope.ALL)`. This is consistent with how `set_effect` stores per key and avoids action-at-a-distance. Contract may be revisited once game rules that use `stop_effect` across overlapping scopes exist.

**Effect packs** — each pack is an `EffectBuilder` that owns a set of named effects. The existing element registry is one such pack (`ElementRegistryBuilder`). Games will compose packs at startup (e.g. elements + spells + UI effects) and pass the composed builder to `EffectManager`. `EffectManager` never knows which packs are active — it only calls `builder(name, config)`.

**Resolution negotiation** — when `_build_effect` is called for a scope, find all entries in `_outputs` whose scopes overlap the given scope and take `max(output.min_resolution for matching outputs)`, falling back to 16 if no outputs match the scope. The effect is still built and run at the fallback resolution; it simply produces no visible output until a matching output exists.

**Scope overlap check** — an output matches a scope if any key of any `ScopeValue` in `output.scopes` appears in `scope.keys`. Inline the check as `any(k in scope.keys for s in output.scopes for k in s.keys)` in both `_build_effect` and `_notify_listeners`. No helper needed.

**Output storage** — `_outputs` is a plain `list[EffectOutput]` set at construction and never mutated. Each output carries its own `min_resolution: int` and `scopes: list[ScopeValue]`. No optimization needed; brute-force lookups are fine for the expected number of outputs (≤ 8).

### Key design constraint

`EffectManager` must remain importable and usable on CircuitPython. No generics, no `dataclasses`, no `typing` at runtime beyond the existing `try/except ImportError` pattern.

### What does not change

- `ScopeValue` / `Scope` — no changes.
- `EffectRenderer`, `EffectState`, `EffectTimer` — no changes.
- The de-duplication of renderers by `id(renderer)` in `update` — already correct, keep it.

### What changes in `EffectOutput`

Two required attributes are added to the interface — concrete subclasses must set these in their `__init__`:
- `min_resolution: int` — the minimum pixel count this output needs; used by the manager during resolution negotiation.
- `scopes: list` — the `ScopeValue` instances this output serves; used by the manager for scope matching.

`update_pixels` changes signature from `update_pixels(self, frame: PixelBuffer)` to `update_pixels(self, frames: list)`. It always receives a list, even when only one effect is active. The output is responsible for compositing (additive, average, layered, etc.). Note: allocating a list per frame is not ideal for CircuitPython — this is a known tradeoff to revisit later.

`create_buffer() -> PixelBuffer` is added as a new method. The manager calls this once per active renderer per output per frame to obtain a correctly-sized buffer before rendering. Outputs return a `PixelBuffer` sized to their actual hardware pixel count. Outputs may return a freshly allocated buffer or a pre-allocated one they reuse between frames — the manager does not retain the buffer after passing it to `update_pixels`.

`register_output` method is removed — outputs are constructor arguments.

## Testing Decisions

**What makes a good test here**: tests drive `EffectManager` through its public methods (`set_effect`, `add_effect`, `stop_effect`, `update`) using a spy `EffectOutput` and a stub `EffectBuilder` that returns a deterministic renderer. Tests assert on what the output *received* (pixel frames, events), not on internal data structures.

**Stub `EffectOutput`** — a simple spy that sets `self.min_resolution = 10` and `self.scopes = [Scope.PERSONAL]` (or parameterised), implements `create_buffer()` returning a fresh `PixelBuffer(10)`, and records all calls to `update_pixels` and `handle_event`. `update_pixels` receives a list; the spy records each call. Lives in `effects/tests/manager/helpers.py` or directly in the test file.

**Stub `EffectBuilder`** — returns a fixed `EffectRenderer` backed by a simple shape and palette. Lets tests verify that `set_effect("fire", ...)` produces output without importing any real effect pack.

**Behaviors to test** (in TDD slice order, each a test-first vertical):

1. `update` with no effects set calls `update_pixels([])` on every registered output
2. `set_effect` followed by `update` sends exactly one pixel frame to an output whose scope matches
3. `set_effect` twice in the same scope sends frames for the second effect only
4. `add_effect` in a populated scope sends a list of two `PixelBuffer`s (one per renderer) to the output on each `update`
5. `stop_effect` causes the output to receive `update_pixels([])` on the next `update`
6. An output whose scopes do not match the active effect's scope receives `update_pixels([])` each frame
7. A renderer shared across two scope keys is updated exactly once per frame
8. An event triggered by a renderer reaches every output in scope
9. Resolution passed to `EffectBuilder` equals the max `min_resolution` of matching outputs

**Prior art**: `effects/tests/manager/test_scope.py` (scope routing logic), `effects/tests/test_render.py` (EffectRenderer + PixelBuffer interaction), `effects/tests/test_effect.py` (step update / value sampling).

## Out of Scope

- Audio and haptic `EffectOutput` drivers — the `EffectOutput` interface is specified here but concrete hardware drivers are separate work.
- Multi-output compositing (splitting a single LED strip across two effects spatially) — deferred.
- CircuitPython optimization of `update_pixels(frames: list[PixelBuffer])` — the per-frame list allocation is a known cost; optimization is out of scope here.
- Persisting or serializing effect state across reboots.
- Any UI or configuration file format for defining effects.
- Changes to `EffectRenderer`, `EffectState`, `Scope`, or `ScopeValue`.

## Further Notes

- The existing `__repr__` on `EffectManager` is correct and useful for debugging; keep it.
- The `_seen` set for de-duplicating renderer updates is the right approach for the add/shared-scope case; tests should verify it. In `update`, `_seen` is reused for both the advance pass (de-dup renderer ticks) and the render pass (de-dup per-output gather) — it is cleared once at the top of the advance pass and again before each output's gather loop.
- Once tests are in place, the TODO comments in `manager.py` should be removed — the tests become the specification.
- This PRD intentionally does not prescribe file layout or method signatures beyond what is already in the codebase. The TDD loop will surface the right shape.
