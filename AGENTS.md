## Agent skills

### Issue tracker

GitHub Issues in `aaronsilinskas/aura-prototype` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`), plus `idea`/`spec`/`grilled` and `wayfinder:*`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` (canonical terms + what to avoid), `docs/domain.md` (the map: module layout, key types, constraints), and `docs/adr/`. Extended design in the Obsidian vault at `~/dev/aura/aura-docs/`. See `docs/agents/domain.md`.

### Other

- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.
- **implement-spec** — repo notes that refine the skill's steps. Read `docs/agents/implement-spec.md` before running it.

**When a workflow step names a skill, invoke it with the Skill tool and follow it precisely before proceeding — unless the step is tagged _(user-run)_, in which case do not invoke it (or its underlying skills) yourself. Pause, tell the user the previous step is done, and ask them to run it as the next step.**

### Spec workflow

1. `to-spec` _(user-run)_ — create the spec as a local document only, at `docs/spec/<slug>.md` (no GH issue yet). Ends by asking the user to run `grill-with-docs`.
2. `grill-with-docs` _(user-run)_ — challenge the spec against the domain docs; update the local spec, `GLOSSARY.md` and `docs/adr/` inline as decisions crystallise. `docs/domain.md` maps code that exists, so the implementation tickets update it as their types land. Keep looping until no open questions remain.
3. Publish — at the tail of `grill-with-docs`, once the design has settled (grilling that began from an `idea` issue first drafts the local spec from the session): the agent asks the user for the go-ahead, moves the spec to a GH issue, deletes the local file and closes any source `idea` as superseded by the spec, then opens a PR with the domain-doc edits from grilling (`GLOSSARY.md`, `docs/adr/`) that references the spec issue, and turns on auto-merge (`gh pr merge --auto --merge`) instead of waiting for CI — the user's go-ahead covers the review. Tickets cite these entries, so they are on `main` before `to-tickets` runs.
4. `to-tickets` _(user-run)_ — split the spec into independently-grabbable implementation tickets.
5. `implement-spec` _(user-run)_ — implement every ticket of the spec on one integration branch, whose PR closes the spec and its tickets. After the PR merges, switch back to `main`.
6. Before that PR merges, verify the spec's acceptance criteria are met.

### Ticket implementation workflow

Invoke the `implement` skill via the Skill tool and follow it.