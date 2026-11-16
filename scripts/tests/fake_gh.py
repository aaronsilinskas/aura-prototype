"""A fake ``gh`` CLI for the triage scripts' tests: one issue to view, and a record of writes."""

import json
import subprocess
from typing import Any

_REPO_URL = "https://github.com/owner/repo"


def gh_issue(
    number: int = 7,
    *,
    body: str = "The wand stops glowing.",
    labels: tuple[str, ...] = ("needs-triage",),
    author: str | None = "reporter",
    state: str = "OPEN",
    kind: str = "issues",
    comments: Any = (),
) -> dict[str, Any]:
    """An issue as ``gh issue view --json`` reports it, with every field the triage steps read.

    *author* ``None`` is a deleted account; *kind* ``pull`` makes it a pull request.
    """
    return {
        "number": number,
        "title": "Wand glow stops after a cast",
        "body": body,
        "labels": [{"name": name, "color": "ffffff"} for name in labels],
        "author": {"login": author, "name": "R"} if author else None,
        "comments": list(comments),
        "state": state,
        "url": f"{_REPO_URL}/{kind}/{number}",
    }


class FakeGh:
    """Stands in for ``subprocess.run`` as ``gh``.

    ``gh issue view`` answers with the issue it was built with, cut to the requested
    ``--json`` fields; every other command succeeds with no output.
    """

    def __init__(self, issue: dict[str, Any] | None = None) -> None:
        self.issue = issue if issue is not None else gh_issue()
        self.calls: list[list[str]] = []
        self.stdin: list[str | None] = []

    def __call__(self, args, **kwargs):
        args = list(args)
        self.calls.append(args)
        self.stdin.append(kwargs.get("input"))
        stdout = ""
        if args[:3] == ["gh", "issue", "view"]:
            fields = args[args.index("--json") + 1].split(",")
            stdout = json.dumps({field: self.issue[field] for field in fields})
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    @property
    def views(self) -> list[list[str]]:
        """The ``gh issue view`` calls, cut to ``gh issue view <number>``."""
        return [call[:4] for call in self.calls if call[:3] == ["gh", "issue", "view"]]

    @property
    def writes(self) -> list[list[str]]:
        """Every call but ``gh issue view``."""
        return [call for call in self.calls if call[:3] != ["gh", "issue", "view"]]
