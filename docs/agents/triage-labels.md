# Triage Labels

Labels used on this repo's issue tracker. Most are **triage roles** the skills speak in terms of; others (like `idea`) sit outside the triage flow.

## Triage roles

The skills speak in terms of five canonical triage roles. This section maps those roles to the actual label strings used in this repo's backlog.

| Canonical role    | Label in our backlog | Meaning                                  |
| ----------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Other labels

These sit **outside** the triage state machine (`triage` ignores them); they mark stages of the idea → spec → tickets pipeline.

| Label  | Used by                                         | Meaning                                                                                                   |
| ------ | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `idea` | `to-idea`                                       | A discovery or idea captured to revisit later — a parking-lot stub, not a spec or a triaged item.          |
| `spec` | `grill-with-docs` (publish step)                | A published spec (product requirements) issue — the source of truth for a feature, ready for `to-tickets`. |

An `idea` is a placeholder you revisit deliberately (`gh issue list --label idea`). A spec is published only at the end of grilling, so every `spec` issue is already grilled and ready for `to-tickets` to break into implementation tickets.

## Wayfinder labels

The `wayfinder` skill speaks in terms of these canonical role labels. This section maps them to the actual label strings used in this repo. See the "Wayfinding operations" section of [issue-tracker.md](issue-tracker.md) for how they're used.

| Canonical role       | Label in our backlog   | Meaning                                                            |
| -------------------- | ---------------------- | ----------------------------------------------------------------- |
| `wayfinder:map`      | `wayfinder:map`        | Marks the map issue — the canonical artifact for a charted effort |
| `wayfinder:research` | `wayfinder:research`   | Research ticket (AFK) — reads docs/APIs via the `research` skill   |
| `wayfinder:prototype`| `wayfinder:prototype`  | Prototype ticket (HITL) — a rough artifact to react to            |
| `wayfinder:grilling` | `wayfinder:grilling`   | Grilling ticket (HITL) — the default decision conversation        |
| `wayfinder:task`     | `wayfinder:task`       | Task ticket — manual work that unblocks a decision                |

These sit outside the triage state machine, like `idea`. Edit the right-hand column to match whatever vocabulary you actually use.

## Automated triage

`needs-triage` is the maintainer's switch for AI triage. Adding it to an open issue (creating the issue with it counts) runs the `Triage` workflow (`.github/workflows/triage.yml`): Claude reads the issue and the repo's committed docs and code read-only and returns a decision, and a separate deterministic step (`scripts/triage_apply.py`) validates it and applies it to that issue only.

- **Who can start a run:** only people with triage access or higher can add labels (and a dispatch needs write access), so in practice only the maintainer. Labels and comments the workflow writes itself start no run, and neither do events from bots.
- **What it sets:** a category (`bug` or `enhancement`, replacing the other) and one state: `needs-info` (with triage notes asking the reporter specific questions), `ready-for-agent` (with an agent brief), `ready-for-human` (read it as "take a look"; an issue bigger than one PR, or needing design discussion, always lands here with a comment saying it needs a spec), or `needs-triage` kept with a recommendation when Claude can't decide. The new state replaces the old one, and it posts one comment starting with the AI disclaimer.
- **What it never does:** close an issue, apply `wontfix`, or touch any other label (`idea`, `spec`, `wayfinder:*`). An invalid decision or a failed run changes nothing, so `needs-triage` stays and the issue stays on the maintainer's list.
- **Re-triage:** re-add `needs-triage`, or dispatch the `Triage` workflow from the Actions tab with the issue number while the issue carries `needs-triage` (a dispatch is a retry, never a bypass). The new run reads the earlier triage notes.
- **Replies and edits start nothing.** A reporter answering a `needs-info` question waits for the maintainer to re-add `needs-triage`.
- **Contributors' issues wait for the maintainer.** An issue someone else opens is left alone until the maintainer adds `needs-triage`.
- **Never add an issue template that auto-applies `needs-triage`.** It would let any reporter start a run.

### Claude credential

The workflow authenticates with the maintainer's Claude subscription through the `CLAUDE_CODE_OAUTH_TOKEN` repository secret. The token expires one year after it is minted; renew it eleven months after minting.

- **Minted:** _not yet_ (record the date here)
- **Renew by:** _eleven months after minting_ (record the date here, and set a calendar reminder for it)

To renew: run `claude setup-token` locally, replace the `CLAUDE_CODE_OAUTH_TOKEN` secret (repo admin), and update the two dates above. An expired or missing token fails the run visibly and leaves `needs-triage` on the issue.

To switch to a Claude Console API key instead, add an `ANTHROPIC_API_KEY` secret and swap the one marked line in the workflow.
