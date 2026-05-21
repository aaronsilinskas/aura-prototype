## Agent skills

- **Backlog** — GH issues in `aaronsilinskas/aura-prototype` via `gh` CLI. See `docs/agents/backlog.md`.
- **Triage labels** — See `docs/agents/triage-labels.md`.
- **Domain docs** — `docs/agents/domain.md` (module layout, key types, vocabulary, constraints). Extended design in Obsidian vault at `~/dev/aura/aura-docs/`.

### PRD workflow

1. `to-prd` — create PRD as a local document only (no GH issue yet).
2. `grill-with-docs` — challenge the PRD; amend the GH issue with decisions reached. **Do NOT create ADRs** — the design is still evolving and ADRs are premature.
3. Keep looping on grilling until no open questions remain.
4. Move the PRD to a GH issue, delete the local file.
5. `to-issues` — split PRD into independently-grabbable implementation issues.
6. `as-work-on-issue` — implement issues in dependency order. After each PR merges, switch back to `main`.
7. When all child issues are closed, verify acceptance criteria are met and close the PRD issue.

### Issue implementation workflow

Follow: https://raw.githubusercontent.com/aaronsilinskas/ai-skills/main/as-work-on-issue/SKILL.md

When assigned an issue via GitHub (not VS Code):
- Skip Step 0 — the assigned issue number is already known
- Skip the `runSubagent` call in Step 0.5 — execute the prompt inside it directly as your own instructions