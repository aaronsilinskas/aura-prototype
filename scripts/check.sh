#!/usr/bin/env bash
# The repo's check command. It syncs the environment itself, so it runs from a
# fresh clone with only uv installed.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --locked
# no-commit-to-branch guards commits, not trees: on a push to main it would fail CI.
SKIP=no-commit-to-branch uv run pre-commit run --all-files --show-diff-on-failure
uv run pytest -q
