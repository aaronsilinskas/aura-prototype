"""Publish a batch of tickets to GitHub as sub-issues of one parent, with blocking edges.

Reads a JSON manifest and creates one issue per ticket, in manifest order, so a
ticket's blockers must appear before it. Each issue becomes a sub-issue of the
parent and gets GitHub's native "blocked by" edges. Afterwards every created
issue is read back and printed as a table, so a wrong title or edge shows up
immediately.

Manifest shape (``body_file`` paths are relative to the manifest)::

    {
      "parent": 1160,
      "labels": ["ready-for-agent"],
      "tickets": [
        {"key": "rename", "title": "...", "body_file": "rename.md"},
        {"key": "declare", "title": "...", "body_file": "declare.md",
         "blocked_by": ["rename"]}
      ]
    }

A ``blocked_by`` entry is a key of an earlier ticket in the manifest, or an
existing issue number.

Usage
-----
    python scripts/publish_tickets.py path/to/tickets.json
    python scripts/publish_tickets.py path/to/tickets.json --dry-run
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

Runner = Callable[[list[str]], str]


class ManifestError(ValueError):
    """The manifest is malformed: a missing field, duplicate key, or bad blocker."""


class Ticket:
    __slots__ = ("blocked_by", "body_file", "key", "title")

    def __init__(self, key: str, title: str, body_file: Path, blocked_by: list[str | int]) -> None:
        self.key = key
        self.title = title
        self.body_file = body_file
        self.blocked_by = blocked_by


def load_manifest(path: Path) -> tuple[int, list[str], list[Ticket]]:
    """Parse and check *path*; every blocker key must name an earlier ticket."""
    data = json.loads(path.read_text())
    try:
        parent = int(data["parent"])
        labels = list(data.get("labels", []))
        raw_tickets = data["tickets"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"{path}: needs an integer 'parent' and a 'tickets' list") from exc

    seen: set[str] = set()
    tickets: list[Ticket] = []
    for raw in raw_tickets:
        try:
            key, title, body = raw["key"], raw["title"], raw["body_file"]
        except KeyError as exc:
            raise ManifestError(f"ticket {raw!r} is missing {exc}") from exc
        if not title.strip():
            raise ManifestError(f"ticket {key!r} has a blank title")
        if key in seen:
            raise ManifestError(f"duplicate ticket key {key!r}")
        body_file = path.parent / body
        if not body_file.is_file():
            raise ManifestError(f"ticket {key!r}: body file {body_file} does not exist")
        blocked_by = list(raw.get("blocked_by", []))
        for blocker in blocked_by:
            if isinstance(blocker, str) and blocker not in seen:
                raise ManifestError(
                    f"ticket {key!r} is blocked by {blocker!r}, which is not an earlier ticket"
                )
        seen.add(key)
        tickets.append(Ticket(key, title, body_file, blocked_by))
    return parent, labels, tickets


def publish(parent: int, labels: list[str], tickets: list[Ticket], run: Runner) -> dict[str, int]:
    """Create every ticket and its edges; returns each key's issue number."""
    numbers: dict[str, int] = {}
    for ticket in tickets:
        cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            ticket.title,
            "--body-file",
            str(ticket.body_file),
        ]
        cmd += ["--parent", str(parent)]
        for label in labels:
            cmd += ["--label", label]
        url = run(cmd).strip().splitlines()[-1]
        numbers[ticket.key] = int(url.rsplit("/", 1)[-1])
        if ticket.blocked_by:
            blockers = ",".join(
                str(numbers[b]) if isinstance(b, str) else str(b) for b in ticket.blocked_by
            )
            run(["gh", "issue", "edit", str(numbers[ticket.key]), "--add-blocked-by", blockers])
    return numbers


def read_back(numbers: dict[str, int], run: Runner) -> list[str]:
    """One table row per created issue, read from GitHub: number, title, blocked-by numbers."""
    rows = ["| # | Title | Blocked by |", "|---|---|---|"]
    for number in numbers.values():
        title = run(
            ["gh", "issue", "view", str(number), "--json", "title", "--jq", ".title"]
        ).strip()
        blockers = run(
            [
                "gh",
                "api",
                f"repos/{{owner}}/{{repo}}/issues/{number}/dependencies/blocked_by",
                "--jq",
                '[.[].number] | map("#\\(.)") | join(", ")',
            ]
        ).strip()
        rows.append(f"| #{number} | {title} | {blockers or '—'} |")
    return rows


def _gh(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="check the manifest and print the plan"
    )
    args = parser.parse_args(argv)

    try:
        parent, labels, tickets = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"parent #{parent}, labels {labels}")
        for ticket in tickets:
            print(f"- {ticket.key}: {ticket.title} (blocked by {ticket.blocked_by or 'none'})")
        return 0

    numbers = publish(parent, labels, tickets, _gh)
    print("\n".join(read_back(numbers, _gh)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
