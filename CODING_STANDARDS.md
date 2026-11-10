# Coding standards

Read at review time (`code-review`), not during implementation. Each source below is authoritative for its area; apply every rule in each.

- **Production code**: `.claude/skills/code-quality/SKILL.md`. For code that runs on the device (`engine/`, `hardware/`, `packs/`), also `.claude/skills/code-quality/embedded-python.md`.
- **Tests**: `.claude/skills/test-quality/SKILL.md` and `.claude/skills/test-quality/mocking-python.md`.
- **Comments and docstrings**: `.claude/skills/comments/SKILL.md` and `.claude/skills/comments/python-docstrings.md`.
- **Terms**: `GLOSSARY.md`. Use its canonical terms and flag the terms it says to avoid.
- **Design decisions**: `docs/adr/`. Flag code that departs from an accepted ADR.

ruff, ruff format, import-linter, basedpyright and pytest run in pre-commit and CI; skip what they enforce. basedpyright fails only on errors missing from `.basedpyright/baseline.json`.

## Judgement calls

- **Docs agree with the change.** When a diff changes behaviour, every prose description of that behaviour must still be true: `README.md`, docstrings, `docs/domain.md` and `GLOSSARY.md`. Search the repo for the changed names and the behaviour's key words, and flag any sentence the diff makes false, including lines the diff never touched.
