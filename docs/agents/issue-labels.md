# Issue Labels

Labels used on this repo's issue backlog. Most are **triage roles** the skills speak in terms of; others (like `idea`) sit outside the triage flow.

## Triage roles

The skills speak in terms of five canonical triage roles. This section maps those roles to the actual label strings used in this repo's backlog.

| Label in mattpocock/skills | Label in our backlog | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
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