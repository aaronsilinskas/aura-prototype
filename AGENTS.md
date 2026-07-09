## Agent skills

- **Backlog** — GH issues in `aaronsilinskas/aura-prototype` via `gh` CLI. See `docs/agents/backlog.md`.
- **Issue labels** — See `docs/agents/issue-labels.md`.
- **Domain docs** — `docs/domain.md` (the map: module layout, key types, constraints) and `docs/domain-language.md` (the glossary: canonical terms + what to avoid). Extended design in Obsidian vault at `~/dev/aura/aura-docs/`.
- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.

**When a workflow step names a skill, invoke it with the Skill tool and follow it precisely before proceeding — unless the step is tagged _(user-run)_, in which case do not invoke it (or its underlying skills) yourself. Pause, tell the user the previous step is done, and ask them to run it as the next step.**

### Spec workflow

1. `to-spec` _(user-run)_ — create the spec as a local document only (no GH issue yet). Ends by asking the user to run `grill-with-docs`.
2. `grill-with-docs` _(user-run)_ — challenge the spec against the domain docs; update the local spec and the domain docs (`docs/domain.md` map + `docs/domain-language.md` glossary) inline as decisions crystallise. Keep looping until no open questions remain.
3. Publish — at the tail of `grill-with-docs`, once the design has settled: the agent asks the user for the go-ahead, then moves the spec to a GH issue and deletes the local file.
4. `to-tickets` _(user-run)_ — split the spec into independently-grabbable implementation tickets.
5. `implement` — work tickets in dependency order. After each PR merges, switch back to `main`.
6. When all child tickets are closed, verify acceptance criteria are met and close the spec issue.

### Ticket implementation workflow

Invoke the `implement` skill via the Skill tool and follow it.