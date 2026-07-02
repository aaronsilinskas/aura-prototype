## Agent skills

- **Backlog** — GH issues in `aaronsilinskas/aura-prototype` via `gh` CLI. See `docs/agents/backlog.md`.
- **Issue labels** — See `docs/agents/issue-labels.md`.
- **Domain docs** — `docs/domain.md` (the map: module layout, key types, constraints) and `docs/domain-language.md` (the glossary: canonical terms + what to avoid). Extended design in Obsidian vault at `~/dev/aura/aura-docs/`.
- **deploy-watch** — Deploy a CircuitPython example to the device and capture serial output. See `docs/agents/deploy-watch.md` before using `scripts/deploy_watch.py`.

**When a workflow step names a skill, invoke it with the Skill tool and follow it precisely before proceeding.**

### PRD workflow

1. `to-prd` — create PRD as a local document only (no GH issue yet).
2. `grill-with-docs` — challenge the PRD against the domain docs; update the local PRD and the domain docs (`docs/domain.md` map + `docs/domain-language.md` glossary) inline as decisions crystallise.
3. Keep looping on grilling until no open questions remain.
4. Move the PRD to a GH issue, delete the local file.
5. `to-issues` — split PRD into independently-grabbable implementation issues.
6. `work-on-issue` — implement issues in dependency order. After each PR merges, switch back to `main`.
7. When all child issues are closed, verify acceptance criteria are met and close the PRD issue.

### Issue implementation workflow

Invoke the `work-on-issue` skill via the Skill tool and follow it.