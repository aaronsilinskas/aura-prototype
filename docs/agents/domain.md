# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This is a **single-context** repo.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root: canonical code-facing terms and the words to avoid.
- **`docs/domain.md`**: the domain map (module layout, key types, constraints). Term meanings live in the glossary, not here.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.
- **`~/dev/aura/aura-docs/`** (Obsidian vault): game and hardware design, including magic-system vocabulary (elements, auras, spells). Read the relevant notes when a task touches game rules or props.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── GLOSSARY.md
├── docs/
│   ├── domain.md
│   └── adr/
│       └── 0001-....md
└── effects/, engine/, magic/, ...
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
