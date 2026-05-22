# PRD: Hardware Test Scene — Component Verification Without Game Play

**Status:** Draft
**Author:** Aaron H
**Created:** 2026-05-21
**Prerequisites:** Issue #85 (Scene — SceneManager), Issue #90 (call site migration — pack-prefixed names)

---

## Problem Statement

During hardware bring-up and field testing, verifying that RGB strips, sound,
vibration, IR, and radio all work correctly requires either running a full game
or writing one-off scripts. There is no reusable, loadable scene that exercises
each hardware component in isolation and provides immediate feedback per
component.

The existing `debug_pack` (now `packs/rules/debug_pack/`) only logs events; it
has no visual or haptic output, no network round-trip test, and no motion
response. Replacing it with a real scene is blocked until `SceneManager` lands
(#85).

---

## Solution

A `hw_test` scene loadable by `SceneManager` that exercises hardware components
one category at a time via a **test mode**. Button B cycles through modes; each
mode dedicates all three scopes to a single hardware subsystem:

| Mode | What is tested | Scopes used |
|------|---------------|-------------|
| RGB | Ambient effects, distinct element per scope | One element per scope, idle |
| IMU | Accelerometer x/y/z — each axis drives a scope's effect level | `PERSONAL`=x, `DIRECTIONAL`=y, `Global.MAIN`=z |
| IR | Button A sends test IR; receive changes a scope's effect | `DIRECTIONAL` reacts to receive |
| Radio | Button A sends test radio packet; receive changes a scope's effect | `Global.MAIN` reacts to receive |

Switching modes via Button B restores all scopes to a dim idle effect before
starting mode-specific behaviour. Button A performs the active action for the
current mode (send IR, send radio; no-op in RGB/IMU modes).

---

## User Stories

1. As a hardware developer, I want to load the hw_test scene and immediately see
   a distinct effect on each scope (RGB mode) so I can confirm all RGB outputs
   are wired and responding.
2. As a hardware developer, I want to press Button B to cycle to the next test
   mode so I can focus on one hardware subsystem at a time.
3. As a hardware developer, I want the current mode to be visible (each mode uses
   a recognisably different element) so I always know which subsystem I am
   testing.
4. As a hardware developer, I want IMU mode to map x/y/z acceleration to
   `PERSONAL`/`DIRECTIONAL`/`Global.MAIN` effect levels respectively so I can
   verify each accelerometer axis drives the correct output.
5. As a hardware developer, I want effect level in IMU mode to scale with
   acceleration magnitude so I can see a clear visual response to movement
   intensity.
6. As a hardware developer, I want pressing Button A in IR mode to enqueue a test
   IR-received event so I can verify the full IR receive path without a second
   device.
7. As a hardware developer, I want the `DIRECTIONAL` scope's effect to change
   when the IR-received event fires so I can confirm the IR receive rule is
   wired correctly.
8. As a hardware developer, I want pressing Button A in Radio mode to enqueue a
   test radio-received event so I can verify the radio receive path in isolation.
9. As a hardware developer, I want the `Global.MAIN` scope's effect to change
   when the radio-received event fires so I can confirm radio receive
   independently of IR receive.
10. As a hardware developer, I want Button A to be a no-op in RGB and IMU modes
    so accidental presses do not disrupt the test in progress.
11. As a hardware developer, I want switching modes to reset all scopes to a dim
    idle effect before starting mode-specific behaviour so there is no visual
    bleed from the previous mode.
12. As a hardware developer, I want all interactions to be self-contained within
    the scene so I can load it on any prop without modifying existing game logic.
13. As a game developer, I want the hw_test scene to use `SceneManager` and the
    standard `PackRegistry` / effect-pack system so it exercises those APIs under
    real-device conditions.
14. As a game developer, I want the hw_test scene to declare its own `on_load`
    callback so all idle effects start immediately when the scene loads.

---

## Implementation Decisions

### Scene location: `scenes/hw_test/`

Introduce a top-level `scenes/` directory as the first-party home for reusable
game scenes. Scenes are not discovered by `PackRegistry.scan_dir()` — they are
registered by name with `SceneManager.register()` — so they do not follow the
pack directory conventions (`version.txt`, extractor). A scene module simply
exports a zero-arg factory function.

Initial layout:
```
scenes/
  hw_test/
    __init__.py
    scene.py    — exports factory(): Scene
    rules.py    — HwTestModeRule, HwTestMotionRule, HwTestNetworkRule
```

### Test modes and mode cycling

Mode is an integer stored in `GameState.data["hw_mode"]`. Four modes, cycled by
Button B:

| # | Name | Button A action | Scope effects |
|---|------|----------------|---------------|
| 0 | RGB | no-op | Distinct idle element per scope (fire / water / lightning) |
| 1 | IMU | no-op | Axis-level mapping — x→PERSONAL, y→DIRECTIONAL, z→Global.MAIN |
| 2 | IR | enqueue `IRReceived` | DIRECTIONAL changes on receive |
| 3 | Radio | enqueue `RadioReceived` | Global.MAIN changes on receive |

On mode switch `HwTestModeRule` calls `stop_effect(Scope.ALL)` then re-starts
the mode's idle effects before returning.

### Ambient / idle effects per mode

**RGB mode** (mode 0): one `set_effect` per scope on entry.

| Scope | Effect | Level |
|-------|--------|-------|
| `Scope.PERSONAL` | `"elements.water"` | 4 |
| `Scope.DIRECTIONAL` | `"elements.fire"` | 4 |
| `Scope.Global.MAIN` | `"elements.lightning"` | 4 |

**IMU mode** (mode 1): same idle setup as RGB; `HwTestMotionRule` overrides
levels each tick (see below).

**IR mode** (mode 2): `PERSONAL` and `Global.MAIN` at idle (level 3);
`DIRECTIONAL` starts at `"elements.earth"` level 3 and flashes to level 9 on
`IRReceived`, then returns to level 3.

**Radio mode** (mode 3): `PERSONAL` and `DIRECTIONAL` at idle (level 3);
`Global.MAIN` starts at `"elements.ice"` level 3 and flashes to level 9 on
`RadioReceived`, then returns to level 3.

### IMU mode: axis-to-scope level mapping

`HwTestMotionRule` fires on every `InputEvents.ButtonAndMovement` tick but only
acts when `GameState.data["hw_mode"] == 1`. For each axis it maps acceleration
magnitude to a level using a linear clamp: `level = clamp(int(abs(accel) / ACCEL_MAX * 10), 1, 10)` where `ACCEL_MAX` is a named constant (proposed: 9.8 m/s²).

| Axis | Scope | Effect |
|------|-------|--------|
| x | `Scope.PERSONAL` | `"elements.fire"` |
| y | `Scope.DIRECTIONAL` | `"elements.water"` |
| z | `Scope.Global.MAIN` | `"elements.earth"` |

Each tick calls `set_effect` (replacing the previous) with the computed level.
Accept the per-tick restart; use short-duration looping effects so the restart
is imperceptible at normal frame rates.

### Network events: IR and Radio receive

`engine/input.py` currently defines only `InputEvents.ButtonAndMovement`. Two
new event types are needed:

- `NetworkEvents.IRReceived(data: bytes)` — fired when an IR packet is received
- `NetworkEvents.RadioReceived(data: bytes, sender: str)` — fired when a radio
  packet is received; `sender` is a device identifier string

These live in a new `engine/network.py` module (not in `engine/input.py` —
network events are a distinct category from physical input).

In IR and Radio modes, Button A queues `NetworkEvents.IRReceived(HW_TEST_PAYLOAD)`
or `NetworkEvents.RadioReceived(HW_TEST_PAYLOAD, sender="local")` directly (no
real hardware transmit required). `HW_TEST_PAYLOAD = b"hw_test"` is a named
constant in `scenes/hw_test/rules.py`.

### Sound and vibration: deferred

`SoundOutput` and `VibrationOutput` `EffectOutput` subclasses do not yet exist.
Sound and vibration test modes are out of scope; they are added as new modes when
audio/haptic `EffectOutput` implementations land.

### `Scene` declaration shape (per #85 design)

```python
Scene(
    rules=[HwTestModeRule(), HwTestMotionRule(), HwTestNetworkRule()],
    effect_packs=[("elements", "1.0")],
    rule_packs=[],
    initial_data={"hw_mode": 0},
    on_load=_on_load,
    on_unload=_on_unload,
)
```

`_on_load(ec)` starts RGB mode idle effects. `_on_unload(ec)` calls
`ec.stop_effect(Scope.ALL)`.

---

## Testing Decisions

Tests should verify external rule behaviour only — not internal state
representation. Prior art: `packs/rules/debug_pack/tests/test_button_events.py`
(rule receives event → queues output event).

Tests to write:

- `HwTestModeRule`: Button B PRESSED advances `state.data["hw_mode"]` from 0→1→2→3→0 (wraps).
- `HwTestModeRule`: on mode advance, `stop_effect(Scope.ALL)` is called and
  mode-appropriate idle effects are started.
- `HwTestModeRule`: Button A PRESSED in IR mode (mode 2) queues
  `NetworkEvents.IRReceived(HW_TEST_PAYLOAD)`.
- `HwTestModeRule`: Button A PRESSED in Radio mode (mode 3) queues
  `NetworkEvents.RadioReceived(HW_TEST_PAYLOAD, "local")`.
- `HwTestModeRule`: Button A PRESSED in RGB mode (mode 0) does nothing.
- `HwTestMotionRule`: only acts when `hw_mode == 1`; does nothing in other modes.
- `HwTestMotionRule`: acceleration on x-axis above `ACCEL_MAX` maps to level 10
  on `Scope.PERSONAL`.
- `HwTestMotionRule`: zero acceleration on all axes maps to level 1 on all three
  scopes.
- `HwTestNetworkRule`: `IRReceived(HW_TEST_PAYLOAD)` calls `set_effect` on
  `Scope.DIRECTIONAL` at level 9.
- `HwTestNetworkRule`: `RadioReceived(HW_TEST_PAYLOAD, ...)` calls `set_effect`
  on `Scope.Global.MAIN` at level 9.
- `NetworkEvents` types: instantiate each, confirm attribute access.

Use a `StubEffectControls` (extend `engine/tests/effects/helpers.py`) to capture
`set_effect`/`stop_effect` calls.

---

## Out of Scope

- Sound and vibration test modes (no `SoundOutput`/`VibrationOutput` yet; add as
  new modes when those land)
- Actual IR and radio hardware transmit drivers
- Network receive hardware drivers (scene tests logic path only)
- Live effect level modulation: `update_effect(receipt, level, options)` and the
  related `EffectOutput` level-awareness feature (passing running level to outputs
  so they can adjust hardware brightness or audio volume). Both belong in a
  separate PRD.
- Persistent scene state between loads (scene is stateless across reloads)
- Any game scoring, timers, or multi-device coordination

---

## Further Notes

- This PRD depends on Issue #85 (SceneManager) and Issue #90 (pack-prefixed call
  sites). It should be implemented after both are closed.
- The `scenes/` top-level directory introduced here sets the pattern for future
  reusable first-party scenes (lobby, game, etc.).
- `NetworkEvents` in `engine/network.py` is a small but load-bearing addition —
  it unblocks all future IR/radio rule logic, not just the hw_test scene.
- Motion threshold (2.0 m/s²) is a proposed default; it should be a named
  constant so it can be tuned per-prop without touching rule logic.
