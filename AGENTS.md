## Agent skills

- **Backlog** — GH issues in `aaronsilinskas/aura-prototype` via `gh` CLI. See `docs/agents/backlog.md`.
- **Triage labels** — See `docs/agents/triage-labels.md`.
- **Domain docs** — `docs/agents/domain.md` (module layout, key types, vocabulary, constraints). Extended design in Obsidian vault at `~/dev/aura/aura-docs/`.

### PRD workflow

1. `to-prd` — create PRD as a GH issue.
2. `grill-me` — challenge the PRD; amend the GH issue with decisions reached.
3. Grill again until no open questions remain.
4. `to-issues` — split PRD into independently-grabbable implementation issues.
5. `as-work-on-issue` — implement issues in dependency order. After each PR merges, switch back to `main`.
6. When all child issues are closed, verify acceptance criteria are met and close the PRD issue.