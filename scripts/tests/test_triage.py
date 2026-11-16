"""Tests for scripts.triage: the gate that decides whether an event starts an AI triage run."""

import json
import subprocess
from unittest.mock import patch

import pytest

from scripts.triage import IssueState, TriageEvent, gate, main, read_issue_state


def _open_issue(*labels: str) -> IssueState:
    return IssueState(number=7, is_open=True, is_pull_request=False, labels=frozenset(labels))


def _labeled(label: str) -> TriageEvent:
    return TriageEvent(kind="labeled", issue_number=7, added_label=label, sender_is_bot=False)


def test_adding_needs_triage_to_an_open_issue_that_still_carries_it_runs():
    verdict = gate(_labeled("needs-triage"), _open_issue("needs-triage", "bug"))

    assert verdict.run


def test_adding_any_other_label_skips_even_when_the_issue_carries_needs_triage():
    verdict = gate(_labeled("bug"), _open_issue("needs-triage", "bug"))

    assert not verdict.run


def test_adding_needs_triage_skips_when_the_live_labels_no_longer_include_it():
    verdict = gate(_labeled("needs-triage"), _open_issue("bug"))

    assert not verdict.run


def _dispatch() -> TriageEvent:
    return TriageEvent(
        kind="workflow_dispatch", issue_number=7, added_label=None, sender_is_bot=False
    )


def test_a_dispatch_runs_on_an_open_issue_carrying_needs_triage():
    assert gate(_dispatch(), _open_issue("needs-triage")).run


def test_a_dispatch_skips_an_issue_without_needs_triage():
    assert not gate(_dispatch(), _open_issue("ready-for-agent")).run


_EVENTS_THAT_WOULD_RUN = [_labeled("needs-triage"), _dispatch()]


@pytest.mark.parametrize("event", _EVENTS_THAT_WOULD_RUN, ids=lambda e: e.kind)
def test_a_closed_issue_skips(event):
    closed = IssueState(
        number=7, is_open=False, is_pull_request=False, labels=frozenset({"needs-triage"})
    )

    assert not gate(event, closed).run


@pytest.mark.parametrize("event", _EVENTS_THAT_WOULD_RUN, ids=lambda e: e.kind)
def test_a_pull_request_skips(event):
    pull_request = IssueState(
        number=7, is_open=True, is_pull_request=True, labels=frozenset({"needs-triage"})
    )

    assert not gate(event, pull_request).run


@pytest.mark.parametrize("event", _EVENTS_THAT_WOULD_RUN, ids=lambda e: e.kind)
def test_a_bot_sender_skips(event):
    from_bot = event._replace(sender_is_bot=True)

    assert not gate(from_bot, _open_issue("needs-triage")).run


@pytest.mark.parametrize("kind", ["opened", "edited", "issue_comment"])
def test_any_other_event_kind_skips(kind):
    event = TriageEvent(kind=kind, issue_number=7, added_label="needs-triage", sender_is_bot=False)

    assert not gate(event, _open_issue("needs-triage")).run


def test_each_skip_states_its_own_reason():
    closed = IssueState(number=7, is_open=False, is_pull_request=False, labels=frozenset())
    pull_request = IssueState(number=7, is_open=True, is_pull_request=True, labels=frozenset())
    skips = [
        gate(_labeled("needs-triage")._replace(sender_is_bot=True), _open_issue("needs-triage")),
        gate(_labeled("needs-triage")._replace(kind="opened"), _open_issue("needs-triage")),
        gate(_labeled("bug"), _open_issue("needs-triage")),
        gate(_dispatch(), pull_request),
        gate(_dispatch(), closed),
        gate(_dispatch(), _open_issue()),
    ]

    reasons = [verdict.reason for verdict in skips]
    assert not any(verdict.run for verdict in skips)
    assert all(reasons)
    assert len(set(reasons)) == len(reasons)


# ---------------------------------------------------------------------------
# The gh reader and the command-line wrapper. gh is stubbed: no network.
# ---------------------------------------------------------------------------

_REPO_URL = "https://github.com/owner/repo"


class _FakeGh:
    """Stands in for ``subprocess.run`` as ``gh issue view``, answering with one issue."""

    def __init__(self, state="OPEN", labels=(), kind="issues") -> None:
        self.calls: list[list[str]] = []
        self._state = state
        self._labels = labels
        self._kind = kind

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        number = args[3]
        issue = {
            "state": self._state,
            "labels": [{"name": name, "color": "ffffff"} for name in self._labels],
            "url": f"{_REPO_URL}/{self._kind}/{number}",
        }
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(issue), stderr="")


def _read_with(fake_gh: _FakeGh, number: int = 42) -> IssueState:
    with patch("scripts.triage.subprocess.run", fake_gh):
        return read_issue_state(number)


def test_the_reader_views_the_given_issue_with_gh():
    fake_gh = _FakeGh()

    _read_with(fake_gh, number=42)

    assert [call[:4] for call in fake_gh.calls] == [["gh", "issue", "view", "42"]]


def test_the_reader_reports_the_issues_live_state_and_labels():
    issue = _read_with(_FakeGh(state="OPEN", labels=("needs-triage", "bug")), number=42)

    assert issue == IssueState(
        number=42, is_open=True, is_pull_request=False, labels=frozenset({"needs-triage", "bug"})
    )


@pytest.mark.parametrize("state", ["CLOSED", "MERGED"])
def test_the_reader_reports_any_state_but_open_as_closed(state):
    assert not _read_with(_FakeGh(state=state)).is_open


def test_the_reader_recognises_a_pull_request_by_its_url():
    assert _read_with(_FakeGh(kind="pull")).is_pull_request


def _run_wrapper(args, fake_gh, tmp_path, monkeypatch) -> str:
    """Run the wrapper against *fake_gh* and return what it wrote to the step's outputs."""
    outputs = tmp_path / "github_output"
    outputs.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    with patch("scripts.triage.subprocess.run", fake_gh):
        main(args)
    return outputs.read_text()


def test_the_wrapper_outputs_run_for_a_live_needs_triage_label(tmp_path, monkeypatch):
    fake_gh = _FakeGh(labels=("needs-triage",))

    outputs = _run_wrapper(
        ["--event", "labeled", "--issue", "42", "--label", "needs-triage"],
        fake_gh,
        tmp_path,
        monkeypatch,
    )

    assert outputs == "run=true\n"
    assert [call[:4] for call in fake_gh.calls] == [["gh", "issue", "view", "42"]]


def test_the_wrapper_trusts_the_live_labels_over_the_event(tmp_path, monkeypatch):
    outputs = _run_wrapper(
        ["--event", "labeled", "--issue", "42", "--label", "needs-triage"],
        _FakeGh(labels=("bug",)),
        tmp_path,
        monkeypatch,
    )

    assert outputs == "run=false\n"


def test_the_wrapper_treats_a_bot_sender_type_as_a_bot(tmp_path, monkeypatch):
    outputs = _run_wrapper(
        ["--event", "workflow_dispatch", "--issue", "42", "--sender-type", "Bot"],
        _FakeGh(labels=("needs-triage",)),
        tmp_path,
        monkeypatch,
    )

    assert outputs == "run=false\n"


def test_the_wrapper_logs_the_skip_reason(tmp_path, monkeypatch, capsys):
    _run_wrapper(
        ["--event", "workflow_dispatch", "--issue", "42"],
        _FakeGh(state="CLOSED", labels=("needs-triage",)),
        tmp_path,
        monkeypatch,
    )

    assert "skip: #42 is closed" in capsys.readouterr().out
