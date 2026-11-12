# implement: repo notes

Repo-specific refinements to the `implement` skill. Where a note here differs from the skill, follow the note.

## Work in a worktree, on a ticket branch

The main checkout holds other sessions' uncommitted work, and its `main` moves under you as they pull. Before the first edit, enter a worktree based on `origin/main` (EnterWorktree, name `fix-<issue>-<slug>`), so the branch starts from the remote tip and you stage only your own changes.

## Seams

The issue's acceptance criteria (an agent brief's, when it has one) are the pre-agreed seams `tdd` asks for. Ask about seams only when the issue has no acceptance criteria.

## Commit means: commit, push, open a PR

The skill's "commit your work to the current branch" lands on the worktree's ticket branch. Then push it and open a PR with the `pr` skill, closing the issue (`Closes #<n>`). The PR is the hand-off; the user merges it.

## After the merge

Remove the worktree with `git worktree remove <path>`, after `git -C <path> status --short` prints nothing, and delete the local branch. The remote branch deletes itself on merge.
