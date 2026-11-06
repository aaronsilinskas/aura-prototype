# implement-spec: repo notes

Repo-specific refinements to the `implement-spec` skill. Where a note here differs from the skill, follow the note.

## The main checkout is not the integration base

The main checkout usually holds unrelated uncommitted work (KiCad files under `electronics/`, drafts in progress). Implementers work from the integration branch on `origin`, so the orchestrator reads from `origin` too:

- Read repo files at the integration base with `git show origin/<branch>:<path>`, not from the working copy. An uncommitted draft in the checkout looks committed when read from disk.
- Leave the main checkout on its branch, with its changes in place. Merge and review in a temporary worktree of the integration branch (`git worktree add <scratch-dir> origin/<integration-branch>`), and remove it afterwards.

## Merging a finished ticket (skill step 5)

Merge inline: in a temporary worktree of the integration branch, `git merge --no-ff <ticket-branch>`, run `uv run pytest -q`, then `git push origin HEAD:<integration-branch>`. Hand off to a merger subagent only when the merge conflicts — a clean merge is three commands, and a subagent costs ~35k tokens to run them.
