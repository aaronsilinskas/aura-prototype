---
name: checkout
description: Check out a branch in the project directory to validate and iterate on it, cleaning up a blocking worktree and rescuing local changes first.
argument-hint: "branch to check out (or leave blank to pick from worktrees / recent branches)"
disable-model-invocation: true
---

Bring a branch into the **project directory** (the primary working copy, not a worktree) so you can run, validate, and iterate on it by hand. The usual case: an agent finished work on a branch in its own worktree, and now you want that branch in your main checkout to drive it yourself.

Two things routinely block a clean checkout, and this skill clears both before switching: a **worktree still holding the branch**, and **local changes you don't want to lose**. Work through the steps in order. Each one is a gate for the next.

## 1. Confirm you're in the main project directory

This skill switches the *primary* working copy, so a linked worktree is the wrong place to run it: `git switch` there would move that worktree instead. Check with `git rev-parse --git-common-dir` and `git rev-parse --git-dir`. If they differ, the current directory is a linked worktree. In that case, tell the user which directory is the main one (`git worktree list` shows it first) and ask whether to switch there before proceeding. Don't continue from a worktree.

## 2. Identify the target branch

Take it from the argument. If it's blank, or the branch doesn't exist, help the user choose: list the worktrees (`git worktree list`) and recent branches (`git branch --sort=-committerdate | head`) and ask which one. Confirm the branch actually exists before going further, because checking out a typo'd name wastes the whole sequence. Check locally with `git rev-parse --verify <branch>`, and on the remote with `git ls-remote --heads origin <branch>` (or scan `git branch -r`). A remote-only branch checks out cleanly only when a single remote carries it, so note which remote it came from if there's more than one.

If the target is already the current branch, there's nothing to switch. Skip to step 5 and report where it stands.

## 3. Rescue local changes in the project directory

Run `git status --porcelain`. If it's empty, the working tree is clean, so move on.

If there are uncommitted or unstaged changes, **stop and ask the user** how to preserve them. Never switch branches over top of them; checkout can fail or silently carry them onto the target. Offer the two options:

- **Stash them.** `git stash push --include-untracked -m "checkout: <current-branch> <date>"`. Include untracked files so nothing is left behind. Treat this as parking the work for later, not restoring it now. Popping it onto the target branch you're about to check out would mix it into unrelated code and can conflict. Tell the user to `git stash pop` (or `git stash list` if they've stacked several) once they've switched *back* to where the changes belong.
- **Commit them to a new branch.** Create a branch from the current HEAD so the changes travel with it: `git switch -c <name>`, then `git add -A && git commit`. Suggest a name tied to the current branch (e.g. `wip/<current-branch>`). Now the work is safely on its own branch and the working tree is clean.

Only proceed once the working tree is clean.

## 4. Clear a worktree holding the target branch

Git refuses to check out a branch that's already checked out in another worktree (`fatal: '<branch>' is already checked out at ...`). Find out with `git worktree list`. If a worktree holds the target branch, remove it to unblock the checkout. Cleaning up the finished agent's worktree is the right hygiene anyway.

- If that worktree is clean: `git worktree remove <path>`.
- If it has **uncommitted changes** of its own, `git worktree remove` will refuse. Those changes aren't on the branch, so pulling the branch won't include them. Don't silently `--force` them away. Tell the user what's uncommitted there and ask whether to discard it (`git worktree remove --force <path>`) or hold off so they can commit it in that worktree first.

`git worktree remove` already cleans up its administrative files. Only reach for `git worktree prune` if a worktree directory was deleted by hand out-of-band, leaving stale entries behind.

## 5. Check out, update, and orient for validation

Switch the project directory to the target: `git switch <branch>` (or `git checkout <branch>`; for a branch that only exists on a remote, this sets up tracking automatically).

**Then pull the latest of the branch** so you validate what's actually on the remote, not a stale local copy. This is what makes `/checkout main` bring in new upstream commits instead of leaving you on an old local `main`. Use `git pull --ff-only`: it fast-forwards the branch to its upstream, and when the two have diverged it refuses instead of creating a merge commit. Handle what it reports:

- **Fast-forwarded, or already up to date:** continue.
- **No upstream configured** (a purely local branch, or a fresh remote-only checkout where tracking isn't set yet): there's nothing to pull. Note it and move on.
- **Diverged** (`fatal: Not possible to fast-forward, aborting`): the local branch has commits the remote doesn't. Don't force it. Show the user how they differ (`git log --oneline ..@{u}` for what's on the remote, `@{u}..` for local-only commits) and let them decide whether to rebase, merge, or keep the local version.

Then set the user up to validate and iterate, which is the whole point of pulling it here:

- Show recent commits (`git log --oneline -10`) and how the branch sits relative to its base/remote (ahead/behind).
- Point out anything that needs doing before running: uninstalled dependencies, migrations, a stale lockfile.
- Suggest the next move, such as running the project's checks or driving the app, but let the user take it from here.
