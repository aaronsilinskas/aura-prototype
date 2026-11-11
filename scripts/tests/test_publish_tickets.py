"""Tests for scripts.publish_tickets: manifest checks and the gh commands it issues.

``gh`` is replaced by a recording runner, so no network or GitHub access is needed.
"""

import json
from pathlib import Path

import pytest

from scripts.publish_tickets import (
    DomainDocsError,
    ManifestError,
    load_manifest,
    publish,
    wait_for_domain_docs,
)


def _manifest(tmp_path: Path, tickets: list[dict], parent: int = 100) -> Path:
    for ticket in tickets:
        (tmp_path / ticket.get("body_file", "missing.md")).write_text("body")
    path = tmp_path / "tickets.json"
    path.write_text(
        json.dumps({"parent": parent, "labels": ["ready-for-agent"], "tickets": tickets})
    )
    return path


class _Gh:
    """Records each command; answers ``issue create`` with sequential issue URLs."""

    def __init__(self, first: int = 200) -> None:
        self.calls: list[list[str]] = []
        self._next = first

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        if cmd[1:3] == ["issue", "create"]:
            self._next += 1
            return f"https://github.com/o/r/issues/{self._next - 1}\n"
        return ""


def test_each_ticket_is_created_under_the_parent_with_its_own_title_in_manifest_order(tmp_path):
    path = _manifest(
        tmp_path,
        [
            {"key": "a", "title": "First", "body_file": "a.md"},
            {"key": "b", "title": "Second", "body_file": "b.md"},
        ],
    )
    gh = _Gh()

    numbers = publish(*load_manifest(path), gh)

    creates = [c for c in gh.calls if c[1:3] == ["issue", "create"]]
    assert [c[c.index("--title") + 1] for c in creates] == ["First", "Second"]
    assert all(c[c.index("--parent") + 1] == "100" for c in creates)
    assert numbers == {"a": 200, "b": 201}


def test_blockers_resolve_keys_to_created_numbers_and_pass_existing_numbers_through(tmp_path):
    path = _manifest(
        tmp_path,
        [
            {"key": "a", "title": "First", "body_file": "a.md"},
            {"key": "b", "title": "Second", "body_file": "b.md", "blocked_by": ["a", 42]},
        ],
    )
    gh = _Gh()

    publish(*load_manifest(path), gh)

    assert ["gh", "issue", "edit", "201", "--add-blocked-by", "200,42"] in gh.calls


def test_a_blocker_that_is_not_an_earlier_ticket_is_rejected_before_anything_is_created(tmp_path):
    path = _manifest(
        tmp_path,
        [
            {"key": "b", "title": "Second", "body_file": "b.md", "blocked_by": ["a"]},
            {"key": "a", "title": "First", "body_file": "a.md"},
        ],
    )

    with pytest.raises(ManifestError, match="'a'"):
        load_manifest(path)


def test_a_blank_title_is_rejected(tmp_path):
    path = _manifest(tmp_path, [{"key": "a", "title": " ", "body_file": "a.md"}])

    with pytest.raises(ManifestError):
        load_manifest(path)


def test_a_duplicate_key_is_rejected(tmp_path):
    path = _manifest(
        tmp_path,
        [
            {"key": "a", "title": "First", "body_file": "a.md"},
            {"key": "a", "title": "Again", "body_file": "a.md"},
        ],
    )

    with pytest.raises(ManifestError):
        load_manifest(path)


class _PrStates:
    """Answers the domain-docs PR lookup with *states* in turn; a fake clock advances on sleep."""

    def __init__(self, *states: str) -> None:
        self.calls: list[list[str]] = []
        self.slept: list[float] = []
        self._states = list(states)
        self._now = 0.0

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._now += seconds

    def now(self) -> float:
        return self._now


def _wait(gh: _PrStates, timeout: float = 60, interval: float = 10) -> None:
    wait_for_domain_docs(
        300, gh, sleep=gh.sleep, now=gh.now, timeout=timeout, interval=interval, log=lambda _: None
    )


def test_the_wait_looks_up_the_spec_domain_docs_branch():
    gh = _PrStates("MERGED")

    _wait(gh)

    assert gh.calls[0][:3] == ["gh", "pr", "list"]
    assert gh.calls[0][gh.calls[0].index("--head") + 1] == "spec-300-domain-docs"


def test_a_spec_with_no_domain_docs_pr_is_not_waited_for():
    gh = _PrStates("")

    _wait(gh)

    assert gh.slept == []


def test_a_merged_domain_docs_pr_is_not_waited_for():
    gh = _PrStates("MERGED")

    _wait(gh)

    assert gh.slept == []


def test_an_open_domain_docs_pr_is_polled_until_it_merges():
    gh = _PrStates("OPEN", "OPEN", "MERGED")

    _wait(gh, interval=10)

    assert gh.slept == [10, 10]


def test_a_domain_docs_pr_closed_without_merging_stops_the_publish():
    gh = _PrStates("CLOSED")

    with pytest.raises(DomainDocsError, match="spec-300-domain-docs"):
        _wait(gh)


def test_a_domain_docs_pr_still_open_at_the_timeout_stops_the_publish():
    gh = _PrStates("OPEN")

    with pytest.raises(DomainDocsError):
        _wait(gh, timeout=30, interval=10)

    assert sum(gh.slept) <= 30
