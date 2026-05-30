# PRD: Compound Audio Effects

## Problem Statement

A single running effect instance cannot simultaneously drive a looping sound and a one-shot sound. For example, an `elements.lightning` effect cannot emit a storm-loop on start and then play a strike one-shot each time its renderer fires a mid-effect event. The current `AudioEffectOutput` model — one ambient-loop voice (`Scope.AMBIENT`) and one one-shot voice (any non-ambient scope) — does not support this.

## Solution

Extend `AudioEffectOutput` to support multiple audio voices per effect, and define a convention for how renderer-emitted mid-effect events map to those voices. A compound effect can own a looping background sound and trigger one-shots on top of it, without the one-shot overriding the loop or requiring a second `set_effect` call from the rule.

## User Stories

1. As a developer, I want a single named effect (e.g. `elements.lightning`) to play a looping storm sound when it starts and a distinct strike sound each time the renderer fires a strike event, so that the audio matches the visual in a single effect call.
2. As a developer, I want a one-shot sound to layer over a looping sound owned by the same effect, so that the loop is not interrupted or replaced when the one-shot triggers.
3. As a developer, I want a looping and a one-shot from the same effect to stop cleanly together when the effect's receipt is stopped, so that I don't need to manually manage multiple receipts.
4. As a developer, I want one-shots triggered by renderer events to not replace one-shots triggered by a different concurrent effect, so that two simultaneous compound effects do not stomp each other's audio.
5. As a rule author, I want to start a compound audio effect with a single `add_effect` or `set_effect` call, so that audio wiring in game rules remains simple.
6. As a rule author, I want `EffectReceipt.stop()` to stop all voices owned by an effect (loop and any queued one-shot), so that teardown is still one call.
7. As a developer, I want missing sound files for either voice to be silently ignored (no crash, no partial playback failure), so that effects degrade gracefully on hardware with incomplete sound packs.
8. As a developer, I want the compound audio model to be testable without real hardware, so that CI validates audio routing decisions.

## Implementation Decisions

- **Voice allocation model**: `AudioEffectOutput` should move from a fixed 2-voice model (voice 0 = ambient loop, voice 1 = one-shot) to a voice pool large enough to support simultaneous compound effects. The exact voice count is a hardware tuning decision — CircuitPython's `audiomixer.Mixer` supports up to `voice_count` simultaneous voices.
- **Compound effect convention**: A named effect signals compound audio intent via renderer-emitted events. The convention for mapping event verbs to audio files needs a defined scheme — e.g. `<pack>/sounds/<effect>.<verb>.wav` for one-shots triggered by event verb, and `<pack>/sounds/<effect>.wav` for the start loop. This is the primary open design question.
- **Voice ownership**: Each effect receipt owns its allocated voices for its lifetime. One-shots from renderer events on the same receipt do not displace the ambient loop or one-shots from sibling receipts.
- **`EffectReceipt.stop()` teardown**: Stopping a receipt must drain all voices owned by that receipt — both the loop and any pending one-shot.
- **`PackRegistry.sound_path` extension**: The current API `sound_path(pack, effect_name)` resolves `<pack>/sounds/<effect_name>.wav` for start/loop sounds. Mid-effect one-shots triggered by renderer event verbs should extend this additively: `sound_path(pack, effect_name, verb)` → `<pack>/sounds/<effect_name>.<verb>.wav`. Callers that omit `verb` continue to work as before. No existing API needs to change.
- **CircuitPython constraint**: File handles must be managed carefully — CircuitPython has tight limits on open file handles. The compound model should not hold more open file handles simultaneously than the current 2-voice model.

## Testing Decisions

- Tests must not import `audiobusio`, `audiomixer`, `audiocore`, or `board` — these are CircuitPython-only. `AudioEffectOutput` must remain testable via a spy/stub injection of the mixer and audio bus, or a test-only subclass that skips hardware init.
- Good tests assert observable output routing decisions (which voice plays which file, when it stops) rather than internal state (which attribute holds which receipt).
- Prior art: `engine/tests/effects/test_manager.py` for `EffectManager` routing tests; `hardware/shared/tests/test_matrix_output.py` for hardware output unit tests.

## Out of Scope

- Effects that produce audio only on some outputs and visuals on others using distinct named effects — that is already supported by the scope routing system.
- Global multi-player audio mixing (audio from multiple players playing simultaneously on shared hardware).
- Dynamic volume curves or cross-fading between loops on transition.

## Further Notes

This PRD was deferred from #188 (RLGL Audio). The current design already clarifies the primary open question: each audio effect is its own named renderer (`renders_pixels=False`), so "compound" means a renderer emitting a mid-effect verb event (e.g. `"strike"`) that `AudioEffectOutput` catches and maps to a second WAV file via `sound_path(pack, effect_name, verb)`. The file naming convention follows naturally: start/loop → `sounds/<effect_name>.wav`, mid-effect one-shot → `sounds/<effect_name>.<verb>.wav`. The remaining implementation work is voice ownership, teardown, and ensuring one-shots from sibling receipts don't collide.
