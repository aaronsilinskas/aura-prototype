"""Tests for scripts.publish_spec: preconditions and the git/gh commands it issues.

``git`` and ``gh`` are replaced by a recording runner, so no repo state or network is touched.
"""

from pathlib import Path

import pytest

from scripts.publish_spec import PublishError, publish, split_spec


class _Shell:
    """Records each command and answers the queries publish_spec makes."""

    def __init__(self, branch: str = "main", staged: str = "", status: str = "") -> None:
        self.calls: list[list[str]] = []
        self.bodies: list[str] = []
        self._answers = {
            ("git", "rev-parse"): branch + "\n",
            ("git", "diff"): staged,
            ("git", "status"): status,
            ("issue", "create"): "https://github.com/o/r/issues/300\n",
            ("pr", "create"): "https://github.com/o/r/pull/301\n",
        }

    def __call__(self, cmd: list[str]) -> str:
        self.calls.append(cmd)
        if cmd[1:3] == ["issue", "create"]:
            self.bodies.append(Path(cmd[cmd.index("--body-file") + 1]).read_text())
            return self._answers[("issue", "create")]
        return self._answers.get((cmd[0], cmd[1]), self._answers.get(tuple(cmd[1:3]), ""))

    def ran(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]


def _spec(tmp_path: Path, text: str = "# Retire things\n\n## Problem Statement\n\nWhy.\n") -> Path:
    path = tmp_path / "retire-things.md"
    path.write_text(text)
    return path


def _quiet(_: str) -> None:
    pass


def test_the_spec_issue_takes_its_title_from_the_heading_and_its_body_from_the_rest(tmp_path):
    shell = _Shell()

    number = publish(_spec(tmp_path), None, None, shell, _quiet)

    (create,) = shell.ran("gh", "issue", "create")
    assert create[create.index("--title") + 1] == "Retire things"
    assert create[create.index("--label") + 1] == "spec"
    assert shell.bodies == ["## Problem Statement\n\nWhy.\n"]
    assert number == 300


def test_the_local_spec_file_is_deleted_after_publishing(tmp_path):
    spec = _spec(tmp_path)

    publish(spec, None, None, _Shell(), _quiet)

    assert not spec.exists()


def test_the_source_idea_is_closed_as_superseded_by_the_spec(tmp_path):
    shell = _Shell()

    publish(_spec(tmp_path), 1179, None, shell, _quiet)

    (close,) = shell.ran("gh", "issue", "close")
    assert close[3] == "1179"
    assert close[close.index("--comment") + 1] == "Superseded by spec #300."


def test_without_domain_doc_changes_no_branch_or_pr_is_made(tmp_path):
    shell = _Shell(status="")

    publish(_spec(tmp_path), None, None, shell, _quiet)

    assert not shell.ran("git", "checkout")
    assert not shell.ran("gh", "pr")


def test_domain_doc_changes_ship_alone_in_an_auto_merging_pr_that_references_the_spec(tmp_path):
    shell = _Shell(status=" M GLOSSARY.md\n?? docs/adr/0009-thing.md\n")

    publish(_spec(tmp_path), None, "A Bot <bot@example.com>", shell, _quiet)

    assert shell.ran("git", "checkout", "-b") == [["git", "checkout", "-b", "spec-300-domain-docs"]]
    assert shell.ran("git", "add") == [
        ["git", "add", "--", "GLOSSARY.md", "docs/adr/0009-thing.md"]
    ]
    (commit,) = shell.ran("git", "commit")
    assert commit[-1].endswith("\n\nCo-Authored-By: A Bot <bot@example.com>")
    (pr,) = shell.ran("gh", "pr", "create")
    assert "Refs #300" in pr[pr.index("--body") + 1]
    assert shell.ran("gh", "pr", "merge") == [
        ["gh", "pr", "merge", "--auto", "--merge", "https://github.com/o/r/pull/301"]
    ]


def test_publishing_ends_on_main_without_the_local_docs_branch(tmp_path):
    shell = _Shell(status=" M GLOSSARY.md\n")

    publish(_spec(tmp_path), None, None, shell, _quiet)

    assert shell.calls[-2:] == [
        ["git", "checkout", "main"],
        ["git", "branch", "-D", "spec-300-domain-docs"],
    ]


def test_off_main_nothing_is_published(tmp_path):
    shell = _Shell(branch="feature")

    with pytest.raises(PublishError, match="main"):
        publish(_spec(tmp_path), None, None, shell, _quiet)

    assert not shell.ran("gh")


def test_with_something_already_staged_nothing_is_published(tmp_path):
    shell = _Shell(staged="effects/thing.py\n")

    with pytest.raises(PublishError, match="unstage"):
        publish(_spec(tmp_path), None, None, shell, _quiet)

    assert not shell.ran("gh")


@pytest.mark.parametrize("text", ["## Problem Statement\n", "#   \n\nbody\n", "intro\n# Title\n"])
def test_a_spec_without_a_leading_title_is_rejected(text):
    with pytest.raises(PublishError, match="title"):
        split_spec(text)
