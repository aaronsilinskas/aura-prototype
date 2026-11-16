"""Tests for scripts.triage_secret_check: no credential leaves the Claude job in a decision."""

import base64
import json

import pytest

from scripts.triage_secret_check import carries_secret, main

_TOKEN = "sk-ant-oat01-Q2xhdWRlQ29kZU9BdXRoVG9rZW5Gb3JUZXN0c09ubHlfX19fX19fX19fX19f-AAAA"


def _decision(comment: str) -> str:
    return json.dumps({"category": "bug", "comment": comment, "reasoning": "r"})


def test_a_decision_without_the_secret_is_clean():
    assert not carries_secret(_decision("The wand stops glowing after a cast."), _TOKEN)


def test_the_secret_written_out_is_caught():
    assert carries_secret(_decision(f"Here it is: {_TOKEN}"), _TOKEN)


def test_the_secret_split_across_lines_is_caught():
    middle = len(_TOKEN) // 2
    assert carries_secret(_decision(f"{_TOKEN[:middle]}\n{_TOKEN[middle:]}"), _TOKEN)


def test_a_quarter_of_the_secret_is_caught():
    assert carries_secret(_decision(f"part one: {_TOKEN[20:47]}"), _TOKEN)


@pytest.mark.parametrize("prefix", ["", "x", "xy"], ids=["aligned", "offset 1", "offset 2"])
@pytest.mark.parametrize(
    "encode", [base64.b64encode, base64.urlsafe_b64encode], ids=["base64", "base64url"]
)
def test_the_secret_base64_encoded_inside_other_text_is_caught(prefix, encode):
    encoded = encode(f"{prefix}token={_TOKEN};".encode()).decode()

    assert carries_secret(_decision(encoded), _TOKEN)


def test_the_secret_hex_encoded_is_caught():
    assert carries_secret(_decision(_TOKEN.encode().hex().upper()), _TOKEN)


def test_the_secret_hidden_behind_json_unicode_escapes_is_caught():
    escaped = "".join(f"\\u{ord(char):04x}" for char in _TOKEN)
    raw = '{"comment": "' + escaped + '"}'

    assert carries_secret(raw, _TOKEN)


def test_an_unset_secret_matches_nothing():
    assert not carries_secret(_decision("anything at all"), "")


def _run(monkeypatch, tmp_path, decision: str, **secrets: str) -> str:
    outputs = tmp_path / "github_output"
    outputs.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.setenv("DECISION", decision)
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, secrets.get(name, ""))
    main([])
    return outputs.read_text()


def test_the_step_passes_a_clean_decision_on(monkeypatch, tmp_path):
    outputs = _run(monkeypatch, tmp_path, _decision("fine"), CLAUDE_CODE_OAUTH_TOKEN=_TOKEN)

    assert outputs == "clean=true\n"


@pytest.mark.parametrize("name", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"])
def test_the_step_fails_closed_on_any_credential_in_the_decision(monkeypatch, tmp_path, name):
    with pytest.raises(SystemExit) as failed:
        _run(monkeypatch, tmp_path, _decision(_TOKEN), **{name: _TOKEN})

    assert failed.value.code != 0
    assert (tmp_path / "github_output").read_text() == ""


def test_the_step_never_logs_the_decision(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit):
        _run(monkeypatch, tmp_path, _decision(_TOKEN), CLAUDE_CODE_OAUTH_TOKEN=_TOKEN)

    assert _TOKEN[:16] not in capsys.readouterr().out


@pytest.mark.parametrize("decision", ["", " \n"], ids=["empty", "whitespace"])
def test_the_step_fails_when_claude_produced_no_decision(monkeypatch, tmp_path, capsys, decision):
    with pytest.raises(SystemExit) as failed:
        _run(monkeypatch, tmp_path, decision, CLAUDE_CODE_OAUTH_TOKEN=_TOKEN)

    assert failed.value.code != 0
    assert (tmp_path / "github_output").read_text() == ""
    assert "no credential" not in capsys.readouterr().out
