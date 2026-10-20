# Kotlin KDoc

> Placeholder. Seeded from general KDoc knowledge, not yet from real project experience. Tighten with actual conventions and gotchas as they come up on Kotlin projects.

The decision of *whether* to document a symbol lives in the `comments` skill; this file covers only KDoc formatting.

## Block tags

KDoc uses `@param`, `@return`, and `@throws`/`@exception`, with the same "one tag entry documents one thing" discipline as Python's `Args:`. A `@param` entry describes only that parameter, never the function's broader contract.

```kotlin
/**
 * Validates that all scope keys are valid and bands do not overlap.
 *
 * @param bands mapping of scope key to range
 * @param context label used in error messages
 * @throws IllegalArgumentException if a key is invalid or two bands overlap
 */
fun validateBandMap(bands: Map<String, IntRange>, context: String) { ... }
```

## Symbol references

Use `[Name]` links to reference another class, function, or property. KDoc resolves them to links in generated docs. Reserve backticks/`` `code` `` for inline literals that aren't references.

```kotlin
/** Transmits IR payloads through a [PulseWriter]. */
```

## Property / constructor docs

Prefer `@property` on the class KDoc (or `@constructor`) over duplicating docs on a primary-constructor property. It's the same anti-duplication rule as Python's `__init__`.
