# The effect system installs the scene view at each transition

At every transition (the boot scene, an Overlay, a pop), the **Scene view** is installed into the **Active scene namespace** by the effect system, as part of its transition step. That step is `EffectAdmin`'s "enter the boot scene", "cover" or "uncover". `SceneManager` does not hold the namespace. One **SceneRuntime** builds the namespace, the `EffectManager` that resolves through it, the game engine and `SceneManager` as one matched set.

This reverses part of spec #1112, which made `SceneManager` the one installer and reduced `EffectAdmin` to its merge-strategy snapshot methods. #1112's aims are kept: one install per transition, and one module owning name routing (ADR-0002). What changes is who makes the install. Under #1112, three problems remained:
- **A hand-enforced identity rule.** Every caller had to wire `SceneManager`'s namespace and `EffectAdmin` as faces of the same `EffectManager`, and nothing enforced it.
- **A leaking ordering rule.** `put_back` expected the Overlay's own effects to be stopped first, so `pop` stopped them through the popped state's `EffectControls`, a route `SceneManager`'s own contract forbids.
- **Copied wiring.** The four-object wiring was copied in four places.

## Considered Options

- **`SceneManager` keeps installing, with a single `SceneRuntime` constructor to fix the identity rule.** This removes the copies and the identity rule, but not the ordering rule. Transitions still make two calls into two objects that must agree (one to `EffectAdmin`, one to the namespace).
- **The effect system installs the view inside each transition step (chosen).** The module that resolves names also decides when the view changes. Each transition is one call, and the stop before restoring the covered effects happens inside it.

## Consequences

- `EffectAdmin` moves out of the state module, which hardware imports, into the effect system's own modules. Its steps name the Scene view's types, and import-linter forbids hardware from reaching the scene and namespace modules, even indirectly.
- Demos and profilers that drive an `EffectManager` without a `SceneManager` still install a Scene view on the namespace they build.
