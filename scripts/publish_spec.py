"""Publish a grilled local spec to GitHub and ship the domain-doc edits from grilling.

The publish step at the tail of ``grill-with-docs`` (see the Spec workflow in
``AGENTS.md``), in order:

1. Create the spec issue (label ``spec``): title from the spec's ``# `` heading,
   body is everything after it.
2. Delete the local spec file.
3. Close the source ``idea`` issue (``--idea``) as superseded by the spec.
4. If ``GLOSSARY.md`` or ``docs/adr/`` has changes, commit only those on a new
   ``spec-<N>-domain-docs`` branch, push, open a PR referencing the spec, turn on
   auto-merge, switch back to ``main``, and delete the local branch.

Every precondition is checked before anything leaves the machine: on ``main``,
nothing staged, and the spec has a title. Each step prints as it completes, so a
failure partway through shows exactly what is already done.

Usage
-----
    python scripts/publish_spec.py docs/spec/<slug>.md --idea 1179 \\
        --co-author "Claude Opus 5.5 <noreply@anthropic.com>"
    python scripts/publish_spec.py docs/spec/<slug>.md --dry-run
"""

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

Runner = Callable[[list[str]], str]

DOMAIN_DOC_PATHS = ("GLOSSARY.md", "docs/adr")
PR_FOOTER = "🤖 Generated with [Claude Code](https://claude.com/claude-code)"


class PublishError(ValueError):
    """A precondition failed; nothing has been published."""


def split_spec(text: str) -> tuple[str, str]:
    """Return the spec's ``# `` heading text and the body after it."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            if title:
                return title, "\n".join(lines[i + 1 :]).strip() + "\n"
            break
        if line.strip():
            break
    raise PublishError("the spec must start with a non-blank '# ' title line")


def changed_domain_docs(run: Runner) -> list[str]:
    """Modified or untracked paths under the domain docs (glossary, ADRs)."""
    out = run(["git", "status", "--porcelain", "--untracked-files=all", "--", *DOMAIN_DOC_PATHS])
    return [line[3:] for line in out.splitlines() if line.strip()]


def check_preconditions(run: Runner) -> None:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch != "main":
        raise PublishError(f"run from main (currently on {branch!r})")
    staged = run(["git", "diff", "--cached", "--name-only"]).strip()
    if staged:
        raise PublishError(f"unstage these first, they would ride along in the commit: {staged}")


def publish(
    spec: Path,
    idea: int | None,
    co_author: str | None,
    run: Runner,
    say: Callable[[str], None] = print,
) -> int:
    """Run every step; returns the spec issue number."""
    title, body = split_spec(spec.read_text())
    check_preconditions(run)
    docs = changed_domain_docs(run)

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
        handle.write(body)
    try:
        url = run(
            [
                "gh",
                "issue",
                "create",
                "--label",
                "spec",
                "--title",
                title,
                "--body-file",
                handle.name,
            ]
        )
    finally:
        Path(handle.name).unlink()
    number = int(url.strip().splitlines()[-1].rsplit("/", 1)[-1])
    say(f"spec published: #{number} {title}")

    spec.unlink()
    say(f"deleted {spec}")

    if idea is not None:
        run(
            [
                "gh",
                "issue",
                "close",
                str(idea),
                "--reason",
                "not planned",
                "--comment",
                f"Superseded by spec #{number}.",
            ]
        )
        say(f"closed idea #{idea} as superseded")

    if not docs:
        say("no GLOSSARY.md or docs/adr/ changes: no PR opened")
        return number

    branch = f"spec-{number}-domain-docs"
    message = f"Domain docs for spec #{number}: {title}"
    trailer = f"\n\nCo-Authored-By: {co_author}" if co_author else ""
    run(["git", "checkout", "-b", branch])
    run(["git", "add", "--", *docs])
    run(["git", "commit", "-m", message + trailer])
    run(["git", "push", "-u", "origin", branch])
    pr_body = f"Domain-doc edits from grilling spec #{number}.\n\nRefs #{number}\n\n{PR_FOOTER}"
    pr = run(["gh", "pr", "create", "--title", message, "--body", pr_body]).strip().splitlines()[-1]
    run(["gh", "pr", "merge", "--auto", "--merge", pr])
    run(["git", "checkout", "main"])
    # The PR merges from the pushed branch, so the local copy has no further use.
    run(["git", "branch", "-D", branch])
    say(f"domain-doc PR with auto-merge: {pr} ({', '.join(docs)})")
    return number


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="the local spec file, docs/spec/<slug>.md")
    parser.add_argument("--idea", type=int, help="source idea issue to close as superseded")
    parser.add_argument("--co-author", help="'Name <email>' for the commit's Co-Authored-By")
    parser.add_argument(
        "--dry-run", action="store_true", help="check preconditions and print the plan"
    )
    args = parser.parse_args(argv)

    try:
        title, _ = split_spec(args.spec.read_text())
        check_preconditions(_run)
        docs = changed_domain_docs(_run)
    except (PublishError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"spec: {title}")
        print(f"idea to close: {f'#{args.idea}' if args.idea else 'none'}")
        print(f"domain docs for the PR: {', '.join(docs) or 'none (no PR)'}")
        return 0

    try:
        publish(args.spec, args.idea, args.co_author, _run)
    except subprocess.CalledProcessError as exc:
        print(f"error: {' '.join(exc.cmd)} failed:\n{exc.stderr}", file=sys.stderr)
        print("the steps printed above are done; finish the rest by hand", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
