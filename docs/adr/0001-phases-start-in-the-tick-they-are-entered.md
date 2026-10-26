# Phases start in the tick they are entered

`transition_to` runs the leaving phase's `on_exit`, moves the machine, and runs the entering phase's `on_enter` in one call. The entering phase's handlers skip the event that was being dispatched at entry and hear every event after it. Previously `on_enter` waited for the entering phase's own rule to next be dispatched, so whether a phase started this tick or next depended on rule registration order — which is the alphabetical order of the scene's rule filenames. That lag (~one tick) is invisible on a device, but it made rule order a hidden input: harness tests needed extra slack, hardware_test needed an `AdvancedTo` marker to stop one button press advancing twice, and an IR hit on Tag's first Playing tick was wiped by the late `on_enter`.

## Considered Options

- **Accept and document the lag.** Cheapest, but every new scene would have to know about filename-ordered timing.
- **The engine tells each `PhaseRule` who owns each phase** (extending `_check_phase_owners`). Rejected: phases would only work once rules had passed through `set_rules`/`add_rules`.
- **Each `PhaseRule` registers itself with its scene's `PhaseSlot` at construction (chosen).** Ownership lives next to the machine it belongs to, duplicate owners fail at construction, and the engine no longer knows about phases. Rules and slots are both module-level, so they share a lifetime.

## Consequences

- `on_enter` must not call `transition_to`, and the target of `transition_to` must have an owning `PhaseRule`; both raise.
- A scene's initial phase has no transition, so its `on_enter` still runs on the first dispatch.
- Tests must not construct a second instance of a scene's phase rule against the scene's slot; they use the module's `RULE` or build their own slot.
