#!/usr/bin/env bash
# The repo's check command: the pre-commit hooks on all files (all but
# no-commit-to-branch), then the tests.
# CI runs it on every PR and push to main. It syncs the environment itself, so it
# runs from a fresh clone with only uv installed.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --locked
# no-commit-to-branch guards commits, not trees: on a push to main it would fail CI.
SKIP=no-commit-to-branch uv run pre-commit run --all-files --show-diff-on-failure
uv run pytest -q
