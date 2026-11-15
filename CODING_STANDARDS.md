# Coding standards

Read at review time (`code-review`), not during implementation. Each source below is authoritative for its area; apply every rule in each. Skills are named, not linked: install them as described in `AGENTS.md` ("Working on aura with an agent"). `docs/standards/` holds aura's additions to them, which win where they differ.

- **Production code**: the `code-quality` skill (`code-quality/SKILL.md`). For code that runs on the device (`engine/`, `hardware/`, `packs/`), also `code-quality/embedded-python.md` and `docs/standards/embedded-python.md`.
- **Tests**: the `test-quality` skill (`test-quality/SKILL.md`), `test-quality/mocking-python.md` and `docs/standards/mocking-python.md`.
- **Comments and docstrings**: the `comments` skill (`comments/SKILL.md`) and `comments/python-docstrings.md`.
- **Terms**: `GLOSSARY.md`. Use its canonical terms and flag the terms it says to avoid.
- **Design decisions**: `docs/adr/`. Flag code that departs from an accepted ADR.

ruff, ruff format, import-linter and mypy run in pre-commit and CI; pytest runs in CI. Skip what they enforce.

## Judgement calls

- **Docs agree with the change.** When a diff changes behaviour, every prose description of that behaviour must still be true: `README.md`, docstrings, `docs/domain.md` and `GLOSSARY.md`. Search the repo for the changed names and the behaviour's key words, and flag any sentence the diff makes false, including lines the diff never touched.
