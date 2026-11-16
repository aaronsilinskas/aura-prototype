"""Tests for the triage workflow's Claude step: every restriction in claude_args reaches the CLI.

The workflow's ``claude_args`` goes through claude-code-action's own parser, after the
action's flags, so the tests read it from ``triage.yml`` and run it through a port of that
parser (``scripts.tests.claude_code_action``) rather than a shell.
"""

import json
from pathlib import Path

import pytest
import yaml

from scripts.tests.claude_code_action import (
    SdkOptions,
    agent_mode_claude_args,
    parse_sdk_options,
    shell_quote_parse,
)

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "triage.yml"
_SCHEMA = _ROOT / "scripts" / "triage_decision.schema.json"
_SCHEMA_EXPRESSION = "${{ steps.load.outputs.schema }}"

# The shape of the action's own MCP config on an issue run; its content doesn't matter here.
_ACTION_MCP_CONFIG = json.dumps(
    {
        "mcpServers": {
            "github_comment": {
                "command": "bun",
                "args": ["run", "/home/runner/work/_actions/github-comment-server.ts"],
                "env": {"GITHUB_TOKEN": "ghs_placeholder", "REPO_OWNER": "owner"},
            }
        }
    }
)

# The workflow's settings input sets no permission mode, so the action prefixes auto mode.
_ACTION_PREFIXES = pytest.mark.parametrize(
    "auto_mode", [True, False], ids=["auto mode and MCP config", "MCP config only"]
)


def _workflow_claude_args() -> str:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    (step,) = (step for step in workflow["jobs"]["triage"]["steps"] if step.get("id") == "claude")
    return step["with"]["claude_args"]


def _schema_as_the_load_step_writes_it() -> str:
    """``jq -c 'del(.["$schema"])'``, then every apostrophe as ``\\u0027``."""
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    del schema["$schema"]
    return json.dumps(schema, separators=(",", ":"), ensure_ascii=False).replace("'", "\\u0027")


def _options(auto_mode: bool) -> SdkOptions:
    user_args = _workflow_claude_args()
    assert _SCHEMA_EXPRESSION in user_args
    user_args = user_args.replace(_SCHEMA_EXPRESSION, _schema_as_the_load_step_writes_it())
    return parse_sdk_options(agent_mode_claude_args(user_args, _ACTION_MCP_CONFIG, auto_mode))


@_ACTION_PREFIXES
def test_the_model_and_turn_limit_reach_the_cli(auto_mode):
    options = _options(auto_mode)

    assert (options.model, options.max_turns) == ("sonnet", 10)


@_ACTION_PREFIXES
def test_settings_come_only_from_the_action(auto_mode):
    assert _options(auto_mode).setting_sources == ["user"]


@_ACTION_PREFIXES
def test_the_cli_denies_every_tool_call_no_allow_rule_covers(auto_mode):
    assert _options(auto_mode).permission_mode == "dontAsk"


@_ACTION_PREFIXES
def test_file_reads_inside_the_checkout_are_the_only_allow_rule(auto_mode):
    assert _options(auto_mode).allowed_tools == ["Read(./**)"]


@_ACTION_PREFIXES
def test_every_deny_rule_reaches_the_cli(auto_mode):
    required = {
        *("Bash", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch", "WebSearch"),
        *("mcp__github", "mcp__github_comment", "mcp__github_file_ops"),
        *("mcp__github_inline_comment", "mcp__github_ci"),
        *("Agent", "Task", "Skill", "Workflow", "CronCreate", "RemoteTrigger"),
        *("ScheduleWakeup", "SendMessage", "PushNotification", "EnterWorktree"),
        *("Read(//proc/**)", "Read(//sys/**)", "Read(//dev/**)", "Read(//etc/**)"),
        *("Read(//tmp/**)", "Read(//var/**)", "Read(//run/**)", "Read(//root/**)"),
        *("Read(//opt/**)", "Read(//usr/**)", "Read(~/.*)", "Read(~/.*/**)"),
        *("Read(~/work/_temp/**)", "Read(~/work/_actions/**)", "Read(~/work/_tool/**)"),
        *("Read(~/actions-runner/**)", "Read(~/runners/**)"),
    }

    assert required <= set(_options(auto_mode).disallowed_tools or [])


@_ACTION_PREFIXES
def test_the_decision_schema_reaches_the_cli_intact(auto_mode):
    options = _options(auto_mode)
    expected = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    del expected["$schema"]

    assert options.has_json_schema
    assert json.loads(options.extra_args["json-schema"] or "") == expected


def test_claude_args_holds_no_shell_comment():
    tokens = shell_quote_parse(_workflow_claude_args())

    assert [token for token in tokens if isinstance(token, dict) and "comment" in token] == []
