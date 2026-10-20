# TypeScript TSDoc

> Placeholder. Seeded from general TSDoc/JSDoc knowledge, not yet from real project experience. Tighten with actual conventions and gotchas as they come up on TypeScript projects.

The decision of *whether* to document a symbol lives in the `comments` skill; this file covers only TSDoc formatting.

## Don't restate the types

TypeScript's types already carry parameter and return shapes, so TSDoc leans even harder on *why* than Python docstrings do. Do not add `@param {type}` JSDoc type annotations, because the type annotation is the source of truth. A `@param` tag should add meaning the type can't express, or be omitted entirely.

```typescript
/**
 * Validates that all scope keys are valid and bands do not overlap.
 *
 * @param context - label used in error messages
 * @throws if a key is invalid or two bands overlap
 */
function validateBandMap(bands: Map<string, Range>, context: string): void { ... }
```

## Symbol references

Use `{@link Name}` to cross-reference another symbol so it resolves to a link in generated docs; reserve `` `code` `` for inline literals that aren't references.

```typescript
/** Transmits IR payloads through a {@link PulseWriter}. */
```

## Summary-first

The first paragraph is the summary shown in tooling hovers. Lead with the caller-facing purpose, in one sentence, before any `@remarks`/`@example` block.
