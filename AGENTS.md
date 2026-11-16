## Agent skills

### Issue tracker

GitHub Issues in `aaronsilinskas/aura-prototype` via the `gh` CLI. Before reading or creating issues, see `docs/agents/issue-tracker.md` for the `gh` conventions and gotchas.

### Triage labels

Default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), plus `idea`/`spec` and `wayfinder:*`. See `docs/agents/triage-labels.md`. Adding `needs-triage` to an issue starts automated AI triage on it; see its **Automated triage** section.

### Domain docs

Single-context: root `GLOSSARY.md` (canonical terms + what to avoid), `docs/domain.md` (the map: module layout, key types, constraints), and `docs/adr/`. These are the single source of truth for engine design; `README.md` points at them rather than restating them. Extended game and hardware design lives in the maintainer's private Obsidian vault (`~/dev/aura/aura-docs/`); without it, work from the repo docs. See `docs/agents/domain.md`.

### Other

- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.

### Project facts for shared workflows

- **Check command**: `bash scripts/check.sh`. It syncs the uv environment, runs every hook in `.pre-commit-config.yaml` on all files except `no-commit-to-branch`, then `uv run pytest -q`. CI runs it on every PR and push to `main`.
- **Main checkout**: usually holds unrelated uncommitted work (KiCad files under `electronics/`, drafts in progress). Work in a worktree based on `origin/main`, and read committed files with `git show origin/<branch>:<path>`.
- **Coding standards**: `CODING_STANDARDS.md`.
- **Dependency bumps**: arrive as weekly Dependabot PRs; `.github/dependabot.yml` says what it covers and how bumps are grouped. Don't bump those dependencies in a feature change; review and merge the Dependabot PR. Bump by hand what it skips: versions under a workflow step's `with:`, and `circuitpython-stubs` together with the device firmware.

## Working on aura with an agent

The agent skills these docs name (`tdd`, `code-review`, `code-quality`, `test-quality`, `comments`, `diagnosing-bugs` and others) are not committed here. Install them into your clone from their public sources (both locations are git-ignored):

```sh
npx skills add mattpocock/skills -a claude-code --copy -y
npx skills add aaronsilinskas/ai-skills -a claude-code --copy -y
```

Then, once per clone: `uv sync` and `uv run pre-commit install`.

To make a change: build it with the `tdd` skill, review it with `code-review` against `CODING_STANDARDS.md`, run `bash scripts/check.sh`, and open a PR. Propose larger features as an issue first.

## Maintainer workflows

The maintainer runs the spec and ticket workflows (`to-spec`, `grill-with-docs`, publishing specs and ticket batches, `implement-spec`) from a private home repo that holds those workflow notes and their scripts. They need write access to this repo's issues and labels. If you're not the maintainer, skip them and use the flow above.
