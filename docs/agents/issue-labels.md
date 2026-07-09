# Issue Labels

Labels used on this repo's issue backlog. Most are **triage roles** the skills speak in terms of; others (like `idea`) sit outside the triage flow.

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

| Label   | Used by   | Meaning                                                                 |
| ------- | --------- | ----------------------------------------------------------------------- |
| `idea`  | `to-idea` | A discovery or idea captured to revisit later — a parking-lot stub, not a PRD or a triaged item. |

The `idea` label is **not** part of the triage state machine, and `triage` ignores it. An `idea` issue is a placeholder you revisit deliberately (`gh issue list --label idea`); when you decide to act on it, it graduates through `to-prd` (or a grilling session) into a real PRD and implementation issues.

## Wayfinder labels

The `wayfinder` skill speaks in terms of these canonical role labels. This section maps them to the actual label strings used in this repo. See the "Wayfinding operations" section of [backlog.md](backlog.md) for how they're used.

| Canonical role       | Label in our backlog   | Meaning                                                            |
| -------------------- | ---------------------- | ----------------------------------------------------------------- |
| `wayfinder:map`      | `wayfinder:map`        | Marks the map issue — the canonical artifact for a charted effort |
| `wayfinder:research` | `wayfinder:research`   | Research ticket (AFK) — reads docs/APIs via the `research` skill   |
| `wayfinder:prototype`| `wayfinder:prototype`  | Prototype ticket (HITL) — a rough artifact to react to            |
| `wayfinder:grilling` | `wayfinder:grilling`   | Grilling ticket (HITL) — the default decision conversation        |
| `wayfinder:task`     | `wayfinder:task`       | Task ticket — manual work that unblocks a decision                |

These sit outside the triage state machine, like `idea`. Edit the right-hand column to match whatever vocabulary you actually use.