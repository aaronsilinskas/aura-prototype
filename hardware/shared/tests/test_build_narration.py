"""Behaviour-driven tests for narrate_step / narrate_skip (hardware/shared/build_narration.py).

Covers:
- narrate_step opens the line before the build thunk runs, closes it with the
  thunk's own success suffix, and returns the built value
- a throwing build thunk closes the line FAILED and the exception propagates
  unchanged
- narrate_skip's begin-then-end no-build path
"""

import pytest

from engine.log import Logger
from hardware.shared.build_narration import narrate_skip, narrate_step


def _recording_logger(tag: str = "[hw]") -> tuple[Logger, list[str]]:
    fragments: list[str] = []
    return Logger(tag=tag, sink=fragments.append), fragments


# ---------------------------------------------------------------------------
# narrate_step — success path
# ---------------------------------------------------------------------------


def test_narrate_step_opens_and_closes_the_line_around_a_successful_build():
    logger, fragments = _recording_logger()

    narrate_step(logger, "widget", lambda: ("built", "ok"))

    assert "".join(fragments) == "[hw] widget ok\n"


def test_narrate_step_returns_the_built_value_to_the_caller():
    logger, _ = _recording_logger()

    value = narrate_step(logger, "widget", lambda: ("built-value", "ok"))

    assert value == "built-value"


def test_narrate_step_closes_with_the_builds_own_success_suffix():
    logger, fragments = _recording_logger()

    narrate_step(logger, "ir rx=A0", lambda: (object(), "writer=pio ok"))

    assert "".join(fragments) == "[hw] ir rx=A0 writer=pio ok\n"


# ---------------------------------------------------------------------------
# narrate_step — failure path
# ---------------------------------------------------------------------------


def test_narrate_step_closes_the_line_failed_when_the_build_thunk_raises():
    logger, fragments = _recording_logger()

    def _boom():
        raise ValueError("unknown pin")

    with pytest.raises(ValueError):
        narrate_step(logger, "widget", _boom)

    assert "".join(fragments) == "[hw] widget FAILED\n"


def test_narrate_step_reraises_the_build_thunks_exception_unchanged():
    logger, _ = _recording_logger()
    original = ValueError("unknown pin")

    def _boom():
        raise original

    with pytest.raises(ValueError) as excinfo:
        narrate_step(logger, "widget", _boom)

    assert excinfo.value is original


# ---------------------------------------------------------------------------
# narrate_skip — no-build path
# ---------------------------------------------------------------------------


def test_narrate_skip_emits_begin_then_end_with_no_build_step():
    logger, fragments = _recording_logger()

    narrate_skip(logger, "radio frequency=915.0", "disabled")

    assert "".join(fragments) == "[hw] radio frequency=915.0 disabled\n"
