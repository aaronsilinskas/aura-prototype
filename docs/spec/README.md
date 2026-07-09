# Specs

Specs (product requirements) for aura-prototype, organized as vertical slices of functionality.

## Workflow

1. **Draft** — Use the `to-spec` skill to generate a spec from the current conversation context, or `grill-me` to stress-test a plan before drafting. Save the draft here as `<slug>.md`.
2. **Review** — Iterate on the draft in this folder until approved.
3. **Publish** — Once approved, publish to GitHub Issues using the `to-spec` skill. The issue becomes the source of truth; the local file can be deleted or kept as an archive.

## Format

Each spec follows the standard template:

- **Problem Statement** — the problem from the user's perspective
- **Solution** — the solution from the user's perspective
- **User Stories** — numbered list covering all aspects of the feature
- **Implementation Decisions** — modules, interfaces, architectural choices
- **Testing Decisions** — what will be tested and how
- **Out of Scope** — explicit exclusions
- **Further Notes** — anything else relevant
