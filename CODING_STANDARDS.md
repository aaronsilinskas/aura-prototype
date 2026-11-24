# Coding standards

Read at review time (`code-review`), not during implementation. Each source below is authoritative for its area; apply every rule in each. Skills are named, not linked: install them as described in `AGENTS.md` ("Working on aura with an agent"). `docs/standards/` holds aura's additions to them, which win where they differ.

- **Production code**: the `code-quality` skill (`code-quality/SKILL.md`). For code that runs on the device (`engine/`, `hardware/`, `packs/`), also the `embedded-python` skill (`embedded-python/SKILL.md`) and `docs/standards/embedded-python.md`.
- **Tests**: the `test-quality` skill (`test-quality/SKILL.md`), `test-quality/mocking-python.md` and `docs/standards/mocking-python.md`.
- **Comments and docstrings**: the `comments-backpressure` skill (`comments-backpressure/SKILL.md`) and `comments-backpressure/python-docstrings.md`.
- **Terms**: `GLOSSARY.md`. Use its canonical terms and flag the terms it says to avoid.
- **Design decisions**: `docs/adr/`. Flag code that departs from an accepted ADR.

ruff, ruff format, import-linter, mypy, the section-banner comment check, the work-tracking reference check, actionlint and check-dependabot (which validates `.github/dependabot.yml`) run in pre-commit and in `scripts/check.sh` (which also runs pytest, and which CI runs). Skip what they enforce.

## Judgement calls

- **Docs agree with the change.** When a diff changes behaviour, every prose description of that behaviour must still be true: `README.md`, docstrings, `docs/domain.md` and `GLOSSARY.md`. Search the repo for the changed names and the behaviour's key words, and flag any sentence the diff makes false, including lines the diff never touched.
- **Engine gaps get an engine issue.** Pack docstrings and comments describe what the pack does. When one under `packs/` explains how the pack works around an engine mechanic ("because the engine ...", "silently ignored", "nothing of its own to terminate it"), the fix is an engine issue that removes the need. The comment may stay while that issue is open, linking it by its `issues/<N>` URL; flag a workaround comment without that link.
