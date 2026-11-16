"""What claude-code-action makes of a workflow's ``claude_args``, ported to Python.

Test-only. A faithful port of the action at the SHA ``.github/workflows/triage.yml`` pins
(anthropics/claude-code-action ``f3b070c8``, v1.0.276), so a test can see the options the
Claude CLI really gets:

- ``src/modes/agent/index.ts`` (``prepareAgentMode``): the prefix the action puts in
  front of the workflow's ``claude_args``.
- ``base-action/src/parse-sdk-options.ts``: whole-line comment stripping, the
  metacharacter escape, ``parseClaudeArgsToExtraArgs`` and the claude_args half of
  ``parseSdkOptions``.
- shell-quote 1.8.4's ``parse.js`` (the version ``base-action/bun.lock`` locks), called
  as the action calls it, with no environment. Its quirks are kept: an unquoted ``#``
  anywhere in a word comments out the rest of the whole string, and an unquoted ``$``
  expands to nothing (except a name ``Object.prototype`` holds, such as ``$constructor``,
  which JavaScript expands to that member's source; the port expands it to nothing).

Only the ``claude_args`` path is ported; the action's other inputs (``model``,
``allowed_tools`` and the rest) are taken as unset, as the triage workflow leaves them.
Nor are the options ``run.ts`` adds beside ``claude_args``: its own deny rules, which only
add to the list, and ``ANTHROPIC_MODEL``, which would override ``--model``.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Final

# JavaScript's \s and String.prototype.trim() set, which is not quite Python's.
_JS_SPACE: Final = "".join(
    map(chr, (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B)))
) + "".join(map(chr, (0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF)))

# shell-quote 1.8.4 parse.js, with JavaScript's \s spelled out.
_CONTROL: Final = r"(?:\|\||&&|;;|\|&|<\(|<<<|>>|>&|<&|[&;()|<>])"
_META: Final = "|&;()<> \t"
_BAREWORD: Final = "(\\\\['\"" + _META + "]|[^" + _JS_SPACE + "'\"" + _META + "])+"
_DOUBLE_QUOTED: Final = r'"((\\"|[^"])*?)"'
_SINGLE_QUOTED: Final = r"'((\\'|[^'])*?)'"
_CHUNKER: Final = re.compile(
    "(" + _CONTROL + ")|(" + _BAREWORD + "|" + _DOUBLE_QUOTED + "|" + _SINGLE_QUOTED + ")+"
)
_CONTROL_TOKEN: Final = re.compile(_CONTROL)
_SPECIAL_VARIABLE: Final = re.compile(r"[*@#?$!_-]")
_VARIABLE_END: Final = re.compile(r"[^\w\d_]", re.ASCII)

# parse-sdk-options.ts
_SHELL_META: Final = {char: chr(0xE000 + index) for index, char in enumerate("()|&;<>")}
_SHELL_UNMETA: Final = {escaped: char for char, escaped in _SHELL_META.items()}
_ACCUMULATING_FLAGS: Final = frozenset(
    (
        "allowedTools",
        "allowed-tools",
        "disallowedTools",
        "disallowed-tools",
        "mcp-config",
        "add-dir",
    )
)
_ACCUMULATE_DELIMITER: Final = "\x00"

ShellToken = str | dict[str, str]
"""A shell-quote token: a word, or an object for an operator, a glob or a comment."""


def shell_quote_parse(string: str) -> list[ShellToken]:
    """shell-quote's ``parse(string)``, with no environment, as the action calls it."""
    commented = False
    tokens: list[ShellToken] = []
    for match in _CHUNKER.finditer(string):
        if commented:
            break
        word = match.group(0)
        if _CONTROL_TOKEN.fullmatch(word):
            tokens.append({"op": word})
            continue
        parsed, commented = _parse_word(word, string, match.start())
        tokens.extend(parsed)
    return tokens


def _parse_word(word: str, whole_input: str, start: int) -> tuple[list[ShellToken], bool]:
    """One chunk through shell-quote's scanner, and whether it opened a comment."""
    quote = ""
    escaped = False
    out = ""
    is_glob = False
    i = 0

    def expand_variable() -> str:
        nonlocal i
        i += 1
        char = word[i : i + 1]
        if char == "{":
            i += 1
            if word[i : i + 1] == "}":
                raise ValueError("Bad substitution: " + word[i - 2 : i + 1])
            end = word.find("}", i)
            if end < 0:
                raise ValueError("Bad substitution: " + word[i:])
            name = word[i:end]
            i = end
        elif _SPECIAL_VARIABLE.match(char):
            name = char
            i += 1
        else:
            rest = word[i:]
            stop = _VARIABLE_END.search(rest)
            if stop is None:
                name = rest
                i = len(word)
            else:
                name = rest[: stop.start()]
                i += stop.start() - 1
        # An empty environment: every named variable is unset, and a bare $ stays.
        return "" if name else "$"

    while i < len(word):
        c = word[i]
        is_glob = is_glob or (not quote and c in "*?")
        if escaped:
            out += c
            escaped = False
        elif quote:
            if c == quote:
                quote = ""
            elif quote == "'":
                out += c
            elif c == "\\":
                i += 1
                c = word[i : i + 1]
                out += c if c in ('"', "\\", "$") else "\\" + c
            elif c == "$":
                out += expand_variable()
            else:
                out += c
        elif c in ('"', "'"):
            quote = c
        elif _CONTROL_TOKEN.fullmatch(c):
            return [{"op": word}], False
        elif c == "#":
            comment: ShellToken = {"comment": whole_input[start + i + 1 :]}
            return ([out, comment] if out else [comment]), True
        elif c == "\\":
            escaped = True
        elif c == "$":
            out += expand_variable()
        else:
            out += c
        i += 1
    if is_glob:
        return [{"op": "glob", "pattern": out}], False
    return [out], False


def agent_mode_claude_args(user_args: str, mcp_config: str, auto_mode: bool) -> str:
    """The ``claude_args`` the action hands its parser: its own flags, then the workflow's.

    ``auto_mode`` is ``defaultsToAutoMode()``; ``mcp_config`` is the action's MCP config JSON.
    """
    claude_args = "--permission-mode auto" if auto_mode else ""
    if json.loads(mcp_config).get("mcpServers"):
        escaped = mcp_config.replace("'", "'\\''")
        claude_args = f"{claude_args} --mcp-config '{escaped}'"
    return f"{claude_args} {user_args}".strip(_JS_SPACE)


def parse_claude_args(claude_args: str) -> dict[str, str | None]:
    """``parseClaudeArgsToExtraArgs``: flag name to value, ``None`` for a bare flag.

    Values of an accumulating flag are joined with NUL, across repeats of the flag.
    """
    if not claude_args.strip(_JS_SPACE):
        return {}
    args: list[str] = []
    for token in shell_quote_parse(_escape_shell_meta(_strip_shell_comments(claude_args))):
        if isinstance(token, str):
            args.append(_unescape_shell_meta(token))
        elif "pattern" in token:
            args.append(_unescape_shell_meta(token["pattern"]))

    result: dict[str, str | None] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            flag = arg[2:]
            next_arg = args[i + 1] if i + 1 < len(args) else ""
            if next_arg and not next_arg.startswith("--"):
                if flag in _ACCUMULATING_FLAGS:
                    values = []
                    while i + 1 < len(args) and not args[i + 1].startswith("--"):
                        i += 1
                        values.append(args[i])
                    joined = _ACCUMULATE_DELIMITER.join(values)
                    earlier = result.get(flag)
                    result[flag] = (
                        f"{earlier}{_ACCUMULATE_DELIMITER}{joined}" if earlier else joined
                    )
                else:
                    result[flag] = next_arg
                    i += 1
            else:
                result[flag] = None
        i += 1
    return result


def _strip_shell_comments(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not line.strip(_JS_SPACE).startswith("#"))


def _escape_shell_meta(text: str) -> str:
    return "".join(_SHELL_META.get(char, char) for char in text)


def _unescape_shell_meta(text: str) -> str:
    return "".join(_SHELL_UNMETA.get(char, char) for char in text)


@dataclass(frozen=True)
class SdkOptions:
    """The part of ``parseSdkOptions``' result that ``claude_args`` decides."""

    model: str | None
    max_turns: int | None
    allowed_tools: list[str] | None
    disallowed_tools: list[str] | None
    setting_sources: list[str]
    has_json_schema: bool
    permission_mode: str | None
    """The mode the CLI ends up with: the last ``--permission-mode`` given."""
    extra_args: dict[str, str | None] = field(default_factory=dict)
    """What is left to pass straight through to the CLI, such as ``json-schema``.

    Repeated ``mcp-config`` values stay NUL-joined: the action's merge of them isn't ported.
    """


def parse_sdk_options(claude_args: str) -> SdkOptions:
    """``parseSdkOptions`` for a run whose only option is ``claude_args``."""
    extra_args = parse_claude_args(claude_args)
    has_json_schema = "json-schema" in extra_args
    model = extra_args.pop("model", None) or None
    max_turns = extra_args.pop("max-turns", None) or None
    extra_args.pop("add-dir", None)
    allowed = _tool_rules(
        extra_args.pop("allowedTools", None), extra_args.pop("allowed-tools", None)
    )
    disallowed = _tool_rules(
        extra_args.pop("disallowedTools", None), extra_args.pop("disallowed-tools", None)
    )
    setting_sources = extra_args.pop("setting-sources", None)
    return SdkOptions(
        model=model,
        max_turns=_parse_int(max_turns) if max_turns else None,
        allowed_tools=allowed or None,
        disallowed_tools=disallowed or None,
        setting_sources=setting_sources.split(",")
        if setting_sources
        else ["user", "project", "local"],
        has_json_schema=has_json_schema,
        permission_mode=_last_permission_mode(extra_args),
        extra_args=extra_args,
    )


def _tool_rules(*values: str | None) -> list[str]:
    joined = _ACCUMULATE_DELIMITER.join(value for value in values if value)
    rules = (
        rule.strip(_JS_SPACE)
        for value in joined.split(_ACCUMULATE_DELIMITER)
        for rule in value.split(",")
    )
    return list(dict.fromkeys(rule for rule in rules if rule))


def _parse_int(text: str) -> int | None:
    """JavaScript's ``parseInt(text, 10)``, with ``None`` for NaN."""
    match = re.match(r"[+-]?\d+", text.lstrip(_JS_SPACE), re.ASCII)
    return int(match.group(0)) if match else None


def _last_permission_mode(extra_args: dict[str, str | None]) -> str | None:
    modes: list[str | None] = []
    for flag, value in extra_args.items():
        if flag == "permission-mode":
            modes.append(value)
            continue
        name, equals, inline_value = flag.partition("=")
        if name == "permission-mode":
            modes.append(inline_value if equals else None)
    return modes[-1] if modes else None
