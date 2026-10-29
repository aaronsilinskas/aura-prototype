"""Tests for deploy_watch: watch_stream, discard_until, exit codes, SplitWriter, port selection,
and the CLI's deploy step."""

import functools
import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.deploy import deploy
from scripts.deploy_watch import (
    ConsolePortError,
    SplitWriter,
    discard_until,
    exit_code_for,
    find_console_port,
    parse_args,
    run_deploy,
    select_console_port,
    watch_stream,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def lines(*items: str | None) -> list[str | None]:
    return list(items)


def fixed_clock(start: float = 0.0, step: float = 1.0) -> Callable[[], float]:
    t = [start]

    def _clock() -> float:
        val = t[0]
        t[0] += step
        return val

    return _clock


# ---------------------------------------------------------------------------
# watch_stream: stream_ended
# ---------------------------------------------------------------------------


def test_watch_stream_returns_stream_ended_when_iterable_exhausted() -> None:
    out = io.StringIO()
    result = watch_stream(lines("hello", "world"), out=out)
    assert result.reason == "stream_ended"


def test_watch_stream_echoes_lines_in_order() -> None:
    out = io.StringIO()
    watch_stream(lines("alpha", "beta", "gamma"), out=out)
    assert out.getvalue() == "alpha\nbeta\ngamma\n"


def test_watch_stream_stream_ended_with_no_lines() -> None:
    out = io.StringIO()
    result = watch_stream(lines(), out=out)
    assert result.reason == "stream_ended"


# ---------------------------------------------------------------------------
# watch_stream: matched
# ---------------------------------------------------------------------------


def test_watch_stream_returns_matched_when_until_substring_found() -> None:
    out = io.StringIO()
    result = watch_stream(lines("starting up", "READY", "more output"), until="READY", out=out)
    assert result.reason == "matched"


def test_watch_stream_stops_echoing_after_matched_line() -> None:
    out = io.StringIO()
    watch_stream(lines("first", "STOP", "after"), until="STOP", out=out)
    assert "after" not in out.getvalue()


def test_watch_stream_echoes_matched_line_itself() -> None:
    out = io.StringIO()
    watch_stream(lines("first", "STOP", "after"), until="STOP", out=out)
    assert "STOP" in out.getvalue()


def test_watch_stream_matches_substring_not_full_line() -> None:
    out = io.StringIO()
    result = watch_stream(lines("error: FATAL crash"), until="FATAL", out=out)
    assert result.reason == "matched"


def test_watch_stream_no_match_returns_stream_ended() -> None:
    out = io.StringIO()
    result = watch_stream(lines("line1", "line2"), until="MISSING", out=out)
    assert result.reason == "stream_ended"


# ---------------------------------------------------------------------------
# watch_stream: timed_out
# ---------------------------------------------------------------------------


def test_watch_stream_returns_timed_out_on_idle_only_stream_when_timeout_elapses() -> None:
    out = io.StringIO()
    result = watch_stream(
        iter([None, None, None, None, None]),
        timeout=2.0,
        clock=fixed_clock(0.0, 1.0),
        out=out,
    )
    assert result.reason == "timed_out"


def test_watch_stream_timed_out_with_until_set_but_not_matched() -> None:
    out = io.StringIO()
    result = watch_stream(
        iter([None, None, None]),
        until="NEVER",
        timeout=1.0,
        clock=fixed_clock(0.0, 2.0),
        out=out,
    )
    assert result.reason == "timed_out"


def test_watch_stream_none_items_are_not_echoed() -> None:
    out = io.StringIO()
    watch_stream(
        iter([None, "hello", None]),
        timeout=10.0,
        clock=fixed_clock(0.0, 0.0),
        out=out,
    )
    assert out.getvalue() == "hello\n"


def test_watch_stream_matched_before_timeout() -> None:
    out = io.StringIO()
    result = watch_stream(
        lines("not yet", "FOUND"),
        until="FOUND",
        timeout=100.0,
        clock=fixed_clock(0.0, 0.0),
        out=out,
    )
    assert result.reason == "matched"


def test_watch_stream_timed_out_when_timeout_elapses_after_stream_exhausted() -> None:
    out = io.StringIO()
    result = watch_stream(
        lines("only-line"),
        timeout=1.0,
        clock=fixed_clock(0.0, 0.6),
        out=out,
    )
    assert result.reason == "timed_out"


# ---------------------------------------------------------------------------
# exit_code_for: exit-code mapping
# ---------------------------------------------------------------------------


def test_exit_code_for_stream_ended_with_no_until_is_zero() -> None:
    assert exit_code_for("stream_ended", until=None) == 0


def test_exit_code_for_matched_is_zero() -> None:
    assert exit_code_for("matched", until="TEXT") == 0


def test_exit_code_for_timed_out_with_no_until_is_zero() -> None:
    assert exit_code_for("timed_out", until=None) == 0


def test_exit_code_for_timed_out_with_until_set_is_two() -> None:
    assert exit_code_for("timed_out", until="TEXT") == 2


def test_exit_code_for_stream_ended_with_until_set_is_two() -> None:
    assert exit_code_for("stream_ended", until="MARKER") == 2


def test_exit_code_for_banner_missing_is_three() -> None:
    assert exit_code_for("banner_missing", until=None) == 3


def test_exit_code_for_banner_missing_with_until_set_is_three() -> None:
    assert exit_code_for("banner_missing", until="MARKER") == 3


# ---------------------------------------------------------------------------
# discard_until
# ---------------------------------------------------------------------------


def test_discard_until_returns_true_when_marker_found_before_deadline() -> None:
    result = discard_until(
        iter(["soft reboot", "some noise", "Soft reboot"]),
        "soft reboot",
        deadline=100.0,
        clock=fixed_clock(0.0, 0.0),
    )
    assert result is True


def test_discard_until_consumes_lines_before_marker() -> None:
    consumed: list[str | None] = []
    it = iter(["noise1", "noise2", "soft reboot", "after"])

    discard_until(it, "soft reboot", deadline=100.0, clock=fixed_clock(0.0, 0.0))

    consumed.extend(it)
    assert consumed == ["after"]


def test_discard_until_matches_marker_as_substring_mid_line() -> None:
    result = discard_until(
        iter(["INFO soft reboot happening now"]),
        "soft reboot",
        deadline=100.0,
        clock=fixed_clock(0.0, 0.0),
    )
    assert result is True


def test_discard_until_returns_false_when_deadline_passes_before_marker() -> None:
    result = discard_until(
        iter([None, None, None, None]),
        "soft reboot",
        deadline=2.0,
        clock=fixed_clock(0.0, 1.0),
    )
    assert result is False


def test_discard_until_returns_false_on_idle_only_stream_after_deadline() -> None:
    result = discard_until(
        iter([None, None]),
        "soft reboot",
        deadline=1.0,
        clock=fixed_clock(2.0, 0.0),
    )
    assert result is False


def test_discard_until_returns_false_when_stream_exhausted_before_marker() -> None:
    result = discard_until(
        iter(["no match here", "still nothing"]),
        "soft reboot",
        deadline=100.0,
        clock=fixed_clock(0.0, 0.0),
    )
    assert result is False


# ---------------------------------------------------------------------------
# SplitWriter
# ---------------------------------------------------------------------------


def test_split_writer_writes_to_stdout() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    split.write("hello\n")
    assert stdout.getvalue() == "hello\n"


def test_split_writer_writes_to_file() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    split.write("hello\n")
    assert file_out.getvalue() == "hello\n"


def test_split_writer_both_streams_receive_same_content() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    split.write("line one\n")
    split.write("line two\n")
    assert stdout.getvalue() == file_out.getvalue()


def test_watch_stream_with_split_writer_captures_serial_to_file() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    watch_stream(lines("alpha", "beta", "gamma"), out=split)
    assert file_out.getvalue() == "alpha\nbeta\ngamma\n"


def test_watch_stream_with_split_writer_still_echoes_to_stdout() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    watch_stream(lines("alpha", "beta"), out=split)
    assert stdout.getvalue() == "alpha\nbeta\n"


def test_split_writer_write_returns_primary_stream_count() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)
    result = split.write("hello\n")
    assert result == len("hello\n")


def test_split_writer_flush_flushes_both_streams() -> None:
    flushed: list[str] = []

    class TrackingStream(io.StringIO):
        def __init__(self, name: str) -> None:
            super().__init__()
            self._name = name

        def flush(self) -> None:
            flushed.append(self._name)
            super().flush()

    split = SplitWriter(TrackingStream("primary"), TrackingStream("secondary"))
    split.flush()
    assert flushed == ["primary", "secondary"]


def test_split_writer_file_excludes_lines_written_directly_to_stdout() -> None:
    stdout = io.StringIO()
    file_out = io.StringIO()
    split = SplitWriter(stdout, file_out)

    # Deploy chatter written directly to stdout (bypassing the split) must not
    # appear in file_out — only lines routed through the split reach the file.
    stdout.write("Deploying code.py...\n")
    stdout.write("Copy complete.\n")

    watch_stream(lines("BOOT OK", "sensor=42", "DONE"), out=split)

    assert file_out.getvalue() == "BOOT OK\nsensor=42\nDONE\n"
    assert "Deploying" not in file_out.getvalue()


# ---------------------------------------------------------------------------
# select_console_port
# ---------------------------------------------------------------------------


# A console port alongside a data port needs no case here: repl_comports()
# filters the data channel out before selection.


class _FakeComport:
    def __init__(self, device: str) -> None:
        self.device = device


def test_select_console_port_auto_selects_the_single_console_port() -> None:
    port = select_console_port([_FakeComport("/dev/cu.usbmodem1101")])

    assert port == "/dev/cu.usbmodem1101"


def test_select_console_port_raises_when_no_console_port_found() -> None:
    with pytest.raises(ConsolePortError, match="--port"):
        select_console_port([])


def test_select_console_port_raises_listing_candidates_when_multiple_console_ports_found() -> None:
    with pytest.raises(ConsolePortError, match=r"cu\.usbmodem1101.*cu\.usbmodem2101.*--port"):
        select_console_port(
            [_FakeComport("/dev/cu.usbmodem1101"), _FakeComport("/dev/cu.usbmodem2101")]
        )


def test_find_console_port_returns_an_explicit_port_unchanged() -> None:
    assert find_console_port(explicit_port="/dev/tty.explicit") == "/dev/tty.explicit"


# ---------------------------------------------------------------------------
# CLI deploy step
# ---------------------------------------------------------------------------


def _deploy_from_source(tmp_path: Path) -> "Callable[..., int]":
    """The real ``deploy``, syncing raw source from a tiny tree under *tmp_path*."""
    source = tmp_path / "source"
    (source / "engine").mkdir(parents=True)
    (source / "engine" / "timer.py").write_text("# timer")
    return functools.partial(deploy, source_root=source, use_source=True)


def _cli_args(tmp_path: Path, *extra: str) -> list[str]:
    mount = tmp_path / "mount"
    mount.mkdir()
    example = tmp_path / "example.py"
    example.write_text("# example")
    return [str(example), "--mount", str(mount), "--seconds", "1", *extra]


def test_scene_flag_records_the_scene_as_default_scene_in_deployed_settings(
    tmp_path: Path,
) -> None:
    args = parse_args(_cli_args(tmp_path, "--scene", "hardware_test"))

    rc = run_deploy(args, deploy=_deploy_from_source(tmp_path))

    assert rc == 0
    settings = json.loads((tmp_path / "mount" / "aura-settings.json").read_text())
    assert settings["default_scene"] == "hardware_test"


def test_omitting_scene_flag_deploys_without_writing_settings(tmp_path: Path) -> None:
    args = parse_args(_cli_args(tmp_path))

    rc = run_deploy(args, deploy=_deploy_from_source(tmp_path))

    assert rc == 0
    assert (tmp_path / "mount" / "code.py").read_text() == "# example"
    assert not (tmp_path / "mount" / "aura-settings.json").exists()
