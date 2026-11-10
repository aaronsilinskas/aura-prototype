# implement-spec: repo notes

Repo-specific refinements to the `implement-spec` skill. Where a note here differs from the skill, follow the note.

## The main checkout is not the integration base

The main checkout usually holds unrelated uncommitted work (KiCad files under `electronics/`, drafts in progress). Implementers work from the integration branch on `origin`, so the orchestrator reads from `origin` too:

- Read repo files at the integration base with `git show origin/<branch>:<path>`, not from the working copy. An uncommitted draft in the checkout looks committed when read from disk.
- Leave the main checkout on its branch, with its changes in place. Merge and review in a temporary worktree of the integration branch (`git worktree add <scratch-dir> origin/<integration-branch>`), and remove it afterwards.

## Ticket branches stay local (skill step 4)

Implementer worktrees (`isolation: "worktree"`) share this repo, so the orchestrator sees their branches without a push. Tell each implementer to:

- take over the worktree's branch by renaming it: `git fetch origin && git branch -m ticket-<n> && git reset --hard origin/<integration-branch>`. Renaming leaves no stray `worktree-agent-*` branch behind;
- commit on `ticket-<n>` and keep it local. Only the integration branch goes to `origin`.

## Merging a finished ticket (skill step 5)

Merge inline: in a temporary worktree of the integration branch, `git merge --no-ff <ticket-branch>` (the local branch), run `uv run pytest -q`, then `git push origin HEAD:<integration-branch>`. Hand off to a merger subagent only when the merge conflicts — a clean merge is three commands, and a subagent costs ~35k tokens to run them.

## Cleaning up (skill step 9)

Remove each implementer worktree and the scratch worktree with `git worktree remove <path>`, after `git -C <path> status --short` prints nothing. Then delete each ticket branch with `git branch -D <branch>` once `git rev-list --count origin/<integration-branch>..<branch>` prints `0`, which proves it is merged.
