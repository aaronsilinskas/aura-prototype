## Agent skills

### Issue tracker

GitHub Issues in `aaronsilinskas/aura-prototype` via the `gh` CLI. Before reading or creating issues, see `docs/agents/issue-tracker.md` for the `gh` conventions and gotchas.

### Triage labels

Default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), plus `idea`/`spec` and `wayfinder:*`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` (canonical terms + what to avoid), `docs/domain.md` (the map: module layout, key types, constraints), and `docs/adr/`. These are the single source of truth for engine design; `README.md` points at them rather than restating them. Extended design in the Obsidian vault at `~/dev/aura/aura-docs/`. See `docs/agents/domain.md`.

### Other

- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.

### Project facts for shared workflows

- **Test suite**: `uv run pytest -q`.
- **Main checkout**: usually holds unrelated uncommitted work (KiCad files under `electronics/`, drafts in progress). Work in a worktree based on `origin/main`, and read committed files with `git show origin/<branch>:<path>`.
- **Coding standards**: `CODING_STANDARDS.md`.

## Workflows

Agent sessions for this repo run from the home repo, `mindwidgets/core` (`~/dev/mindwidgets/core`), which pre-approves this directory in its `.claude/settings.json`. Its `AGENTS.md` defines the spec and ticket workflows, the `implement`/`implement-spec` notes, the publish scripts and the skills. This file holds aura's project facts only.
