## Agent skills

- **Backlog** — GH issues in `aaronsilinskas/aura-prototype` via `gh` CLI. See `docs/agents/backlog.md`.
- **Issue labels** — See `docs/agents/issue-labels.md`.
- **Domain docs** — `docs/domain.md` (the map: module layout, key types, constraints) and `docs/domain-language.md` (the glossary: canonical terms + what to avoid). Extended design in Obsidian vault at `~/dev/aura/aura-docs/`.
- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.

**When a workflow step names a skill, invoke it with the Skill tool and follow it precisely before proceeding — unless the step is tagged _(user-run)_, in which case do not invoke it (or its underlying skills) yourself. Pause, tell the user the previous step is done, and ask them to run it as the next step.**

### PRD workflow

1. `to-prd` _(user-run)_ — create PRD as a local document only (no GH issue yet). Ends by asking the user to run `grill-with-docs`.
2. `grill-with-docs` _(user-run)_ — challenge the PRD against the domain docs; update the local PRD and the domain docs (`docs/domain.md` map + `docs/domain-language.md` glossary) inline as decisions crystallise. Keep looping until no open questions remain.
3. Publish — at the tail of `grill-with-docs`, once the design has settled: the agent asks the user for the go-ahead, then moves the PRD to a GH issue and deletes the local file.
4. `to-issues` _(user-run)_ — split PRD into independently-grabbable implementation issues.
5. `work-on-issue` — implement issues in dependency order. After each PR merges, switch back to `main`.
6. When all child issues are closed, verify acceptance criteria are met and close the PRD issue.

### Issue implementation workflow

Invoke the `work-on-issue` skill via the Skill tool and follow it.