"""Automated triage's credential check: no secret leaves the Claude job inside a decision.

Host-only (CPython), run by the triage workflow and never shipped. Claude's decision ends
up in a public issue comment, and the job that runs Claude holds the Claude credential and
a job token. The runner masks a secret only when it appears verbatim, so this check also
looks for fragments of each secret and for its base64 and hex encodings. :func:`carries_secret`
is pure; ``main`` is the workflow step's wrapper, which fails the job rather than pass a
decision on.
"""

import argparse
import base64
import json
import os
import re
import sys
from collections.abc import Iterator, Sequence
from typing import Final

SECRET_ENV_VARS: Final = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN")
"""The environment variables the workflow step carries its secrets in; unset ones are skipped."""

# A run of this many characters from a secret, or from one of its encodings, counts as a leak.
# Long enough that ordinary text never matches by chance, and shorter than any half of a
# credential, so splitting one in two doesn't hide it.
_FRAGMENT: Final = 16
_WHITESPACE: Final = re.compile(r"\s+")


def carries_secret(decision: str, secret: str) -> bool:
    """Whether *decision* holds a 16-character run of *secret*, plain or encoded.

    The plain forms are checked with whitespace removed and with JSON string escapes
    decoded; the encodings are base64, base64url (at each of the three byte alignments a
    secret can sit at inside longer encoded text) and hex in either case.
    """
    if not secret:
        return False
    texts = [decision, *_json_strings(decision)]
    haystacks = {variant for text in texts for variant in (text, _WHITESPACE.sub("", text))}
    haystacks |= {text.lower() for text in haystacks}
    return any(fragment in text for fragment in _fragments(secret) for text in haystacks)


def _json_strings(decision: str) -> Iterator[str]:
    try:
        value = json.loads(decision)
    except json.JSONDecodeError:
        return
    yield from _strings_in(value)


def _strings_in(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_in(item)


def _fragments(secret: str) -> set[str]:
    forms = [secret, secret.encode().hex()]
    data = secret.encode()
    for offset in range(3):
        # Characters of the encoding that depend on the secret's bytes alone.
        start = -(-8 * offset // 6)
        end = 8 * (offset + len(data)) // 6
        for encode in (base64.b64encode, base64.urlsafe_b64encode):
            forms.append(encode(bytes(offset) + data).decode()[start:end])
    return {
        form[i : i + _FRAGMENT] for form in forms for i in range(max(1, len(form) - _FRAGMENT + 1))
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Check ``$DECISION`` against each secret in :data:`SECRET_ENV_VARS`.

    A clean decision writes ``clean=true`` to ``$GITHUB_OUTPUT``. A missing or blank
    decision, or one that carries a secret, writes nothing and exits non-zero, so a run
    where Claude produced no decision shows red. Neither the decision nor the secret is
    logged.
    """
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    decision = os.environ.get("DECISION", "")
    if not decision.strip():
        print("triage secret check: Claude produced no decision; failing the run")
        sys.exit(1)
    leaked = [
        name for name in SECRET_ENV_VARS if carries_secret(decision, os.environ.get(name, ""))
    ]
    if leaked:
        print(f"triage secret check: the decision carries {', '.join(leaked)}; dropping it")
        sys.exit(1)
    print("triage secret check: the decision carries no credential")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as outputs:
        outputs.write("clean=true\n")


if __name__ == "__main__":
    main()
