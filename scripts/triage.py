"""Automated triage's deterministic logic: the gate that decides whether an event starts a run.

Host-only (CPython), run by the triage workflow and never shipped. :func:`gate` is pure: an
event and the issue's live :class:`IssueState` in, a run-or-skip verdict out.
:func:`read_issue_state` is the thin ``gh`` reader for that live state, built on
:func:`view_issue`, the one ``gh issue view`` call every triage step reads an issue with.
``main`` is the gate step's wrapper.
"""

import argparse
import json
import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, NamedTuple

NEEDS_TRIAGE: Final = "needs-triage"

_LABELED: Final = "labeled"
_TRIGGER_KINDS: Final = frozenset({_LABELED, "workflow_dispatch"})


class IssueState(NamedTuple):
    """An issue's live state as GitHub reports it, read fresh rather than from an event payload.

    The gate reads its state and labels; the apply step reads its labels and its author, the
    one login a triage comment may mention.
    """

    number: int
    is_open: bool
    is_pull_request: bool
    labels: frozenset[str]
    author: str


class TriageEvent(NamedTuple):
    """The workflow event that may start a run.

    ``kind`` is the ``issues`` activity type (``labeled``, ``opened``, ...) or another event
    name (``workflow_dispatch``, ``issue_comment``). ``added_label`` is set only for
    ``labeled``.
    """

    kind: str
    issue_number: int
    added_label: str | None
    sender_is_bot: bool


class GateVerdict(NamedTuple):
    run: bool
    reason: str


def gate(event: TriageEvent, issue: IssueState) -> GateVerdict:
    """Decide whether *event* starts a triage run on *issue*.

    Every trigger, a dispatch included, needs the issue open, not a pull request, and
    carrying ``needs-triage`` live, so a dispatch is a retry and never a bypass.
    """
    if event.sender_is_bot:
        return GateVerdict(False, "the sender is a bot")
    if event.kind not in _TRIGGER_KINDS:
        return GateVerdict(False, f"{event.kind!r} events never start a triage run")
    if event.kind == _LABELED and event.added_label != NEEDS_TRIAGE:
        return GateVerdict(False, f"the added label is {event.added_label!r}, not {NEEDS_TRIAGE!r}")
    if issue.is_pull_request:
        return GateVerdict(False, f"#{issue.number} is a pull request")
    if not issue.is_open:
        return GateVerdict(False, f"#{issue.number} is closed")
    if NEEDS_TRIAGE not in issue.labels:
        return GateVerdict(False, f"#{issue.number} does not carry {NEEDS_TRIAGE!r}")
    return GateVerdict(True, f"#{issue.number} is open and carries {NEEDS_TRIAGE!r}")


def view_issue(number: int, fields: Iterable[str]) -> dict[str, Any]:
    """Read *fields* of issue *number* with ``gh issue view --json``; raises if ``gh`` fails."""
    result = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", ",".join(fields)],
        capture_output=True,
        text=True,
        check=True,
    )
    issue: dict[str, Any] = json.loads(result.stdout)
    return issue


def login(user: Mapping[str, Any] | None) -> str:
    """A ``gh`` user's login; GitHub reports a deleted account as no user, read as ``ghost``."""
    return user["login"] if user else "ghost"


def label_names(issue: Mapping[str, Any]) -> frozenset[str]:
    """The names of a ``gh issue view --json labels`` issue's labels."""
    return frozenset(label["name"] for label in issue["labels"])


def read_issue_state(number: int) -> IssueState:
    """Read issue *number*'s live :class:`IssueState`; raises if ``gh`` fails.

    ``gh issue view`` also answers for a pull request number, which only its URL tells apart.
    """
    issue = view_issue(number, ("state", "labels", "url", "author"))
    return IssueState(
        number=number,
        is_open=issue["state"] == "OPEN",
        is_pull_request="/pull/" in issue["url"],
        labels=label_names(issue),
        author=login(issue["author"]),
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Gate one event: log the verdict and write ``run=true|false`` to ``$GITHUB_OUTPUT``.

    Only ``run`` is written as an output, so no event-supplied text reaches the outputs file.
    """
    parser = argparse.ArgumentParser(description="Decide whether an event starts a triage run.")
    parser.add_argument("--event", required=True, help="issues activity type, or event name")
    parser.add_argument("--issue", required=True, type=int, help="the issue number")
    parser.add_argument("--label", help="the added label, for a labeled event")
    parser.add_argument("--sender-type", default="User", help="the event sender's type")
    args = parser.parse_args(argv)

    event = TriageEvent(
        kind=args.event,
        issue_number=args.issue,
        added_label=args.label,
        sender_is_bot=args.sender_type == "Bot",
    )
    verdict = gate(event, read_issue_state(event.issue_number))

    print(f"triage gate: {'run' if verdict.run else 'skip'}: {verdict.reason}")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as outputs:
        outputs.write(f"run={'true' if verdict.run else 'false'}\n")


if __name__ == "__main__":
    main()
