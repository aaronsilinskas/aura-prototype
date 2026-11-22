"""Tests for deploy_watch: watch_stream, discard_until, exit codes, SplitWriter,
reading serial lines, and the CLI's deploy step."""

import io
import itertools
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

import serial

from scripts.deploy import CompiledBuild, DeployError, DeployPlan, SourceBuild
from scripts.deploy_watch import (
    SerialHandle,
    SplitWriter,
    WatchReason,
    discard_until,
    exit_code_for,
    iter_serial_lines,
    parse_args,
    run_deploy,
    watch_stream,
)
from scripts.tests.helpers import FakeToolchain

if TYPE_CHECKING:
    from serial import Serial

_REPO_ROOT = Path(__file__).parents[2]


def lines(*items: str | None) -> list[str | None]:
    return list(items)


def fixed_clock(start: float = 0.0, step: float = 1.0) -> Callable[[], float]:
    t = [start]

    def _clock() -> float:
        val = t[0]
        t[0] += step
        return val

    return _clock


def test_watch_stream_returns_stream_ended_when_iterable_exhausted() -> None:
    out = io.StringIO()
    result = watch_stream(lines("hello", "world"), out=out)
    assert result.reason is WatchReason.STREAM_ENDED


def test_watch_stream_echoes_lines_in_order() -> None:
    out = io.StringIO()
    watch_stream(lines("alpha", "beta", "gamma"), out=out)
    assert out.getvalue() == "alpha\nbeta\ngamma\n"


def test_watch_stream_stream_ended_with_no_lines() -> None:
    out = io.StringIO()
    result = watch_stream(lines(), out=out)
    assert result.reason is WatchReason.STREAM_ENDED


def test_watch_stream_returns_matched_when_until_substring_found() -> None:
    out = io.StringIO()
    result = watch_stream(lines("starting up", "READY", "more output"), until="READY", out=out)
    assert result.reason is WatchReason.MATCHED


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
    assert result.reason is WatchReason.MATCHED


def test_watch_stream_no_match_returns_stream_ended() -> None:
    out = io.StringIO()
    result = watch_stream(lines("line1", "line2"), until="MISSING", out=out)
    assert result.reason is WatchReason.STREAM_ENDED


def test_watch_stream_returns_timed_out_on_idle_only_stream_when_timeout_elapses() -> None:
    out = io.StringIO()
    result = watch_stream(
        iter([None, None, None, None, None]),
        timeout=2.0,
        clock=fixed_clock(0.0, 1.0),
        out=out,
    )
    assert result.reason is WatchReason.TIMED_OUT


def test_watch_stream_timed_out_with_until_set_but_not_matched() -> None:
    out = io.StringIO()
    result = watch_stream(
        iter([None, None, None]),
        until="NEVER",
        timeout=1.0,
        clock=fixed_clock(0.0, 2.0),
        out=out,
    )
    assert result.reason is WatchReason.TIMED_OUT


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
    assert result.reason is WatchReason.MATCHED


def test_watch_stream_timed_out_when_timeout_elapses_after_stream_exhausted() -> None:
    out = io.StringIO()
    result = watch_stream(
        lines("only-line"),
        timeout=1.0,
        clock=fixed_clock(0.0, 0.6),
        out=out,
    )
    assert result.reason is WatchReason.TIMED_OUT


def test_exit_code_for_stream_ended_with_no_until_is_zero() -> None:
    assert exit_code_for(WatchReason.STREAM_ENDED, until=None) == 0


def test_exit_code_for_matched_is_zero() -> None:
    assert exit_code_for(WatchReason.MATCHED, until="TEXT") == 0


def test_exit_code_for_timed_out_with_no_until_is_zero() -> None:
    assert exit_code_for(WatchReason.TIMED_OUT, until=None) == 0


def test_exit_code_for_timed_out_with_until_set_is_two() -> None:
    assert exit_code_for(WatchReason.TIMED_OUT, until="TEXT") == 2


def test_exit_code_for_stream_ended_with_until_set_is_two() -> None:
    assert exit_code_for(WatchReason.STREAM_ENDED, until="MARKER") == 2


def test_exit_code_for_banner_missing_is_three() -> None:
    assert exit_code_for(WatchReason.BANNER_MISSING, until=None) == 3


def test_exit_code_for_banner_missing_with_until_set_is_three() -> None:
    assert exit_code_for(WatchReason.BANNER_MISSING, until="MARKER") == 3


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


def _cli_args(tmp_path: Path, *extra: str) -> list[str]:
    mount = tmp_path / "mount"
    mount.mkdir()
    example = tmp_path / "example.py"
    example.write_text("# example")
    return [str(example), "--mount", str(mount), "--seconds", "1", *extra]


def _planned(argv: list[str], toolchain: FakeToolchain | None = None) -> DeployPlan:
    """The Deploy plan deploy-watch hands its executor for *argv*."""
    plans: list[DeployPlan] = []
    run_deploy(parse_args(argv), toolchain=toolchain or FakeToolchain(), execute=plans.append)
    [plan] = plans
    return plan


def _failing_executor(plan: DeployPlan) -> None:
    raise DeployError("mpy-cross failed on engine/timer.py: SyntaxError: oops")


def test_scene_flag_asks_to_record_that_scene(tmp_path: Path) -> None:
    plan = _planned(_cli_args(tmp_path, "--scene", "hardware_test"))

    assert plan.scene == "hardware_test"


def test_omitting_scene_flag_asks_to_record_no_scene(tmp_path: Path) -> None:
    plan = _planned(_cli_args(tmp_path))

    assert plan.scene is None


def test_source_flag_deploys_raw_source(tmp_path: Path) -> None:
    plan = _planned(_cli_args(tmp_path, "--source"))

    assert plan.build_choice == SourceBuild()


def test_omitting_source_flag_deploys_compiled_modules(tmp_path: Path) -> None:
    toolchain = FakeToolchain()

    plan = _planned(_cli_args(tmp_path), toolchain)

    assert plan.build_choice == CompiledBuild(toolchain)


def test_failed_deploy_returns_1_and_prints_the_error_line(tmp_path: Path, capsys) -> None:
    args = parse_args(_cli_args(tmp_path))

    rc = run_deploy(args, toolchain=FakeToolchain(), execute=_failing_executor)

    assert rc == 1
    assert capsys.readouterr().err == (
        "Error: mpy-cross failed on engine/timer.py: SyntaxError: oops\n"
    )


def _missing_mount_args(tmp_path: Path) -> list[str]:
    return [str(tmp_path / "example.py"), "--mount", str(tmp_path / "missing"), "--seconds", "1"]


def test_refused_plan_returns_1_and_prints_the_error_line(tmp_path: Path, capsys) -> None:
    args = parse_args(_missing_mount_args(tmp_path))

    rc = run_deploy(args, toolchain=FakeToolchain(), execute=lambda plan: None)

    assert rc == 1
    assert capsys.readouterr().err == (
        f"Error: mount path '{tmp_path / 'missing'}' does not exist or is not a directory.\n"
    )


def test_refused_plan_executes_nothing(tmp_path: Path) -> None:
    plans: list[DeployPlan] = []
    args = parse_args(_missing_mount_args(tmp_path))

    run_deploy(args, toolchain=FakeToolchain(), execute=plans.append)

    assert plans == []


def test_successful_deploy_returns_0(tmp_path: Path) -> None:
    args = parse_args(_cli_args(tmp_path))

    assert run_deploy(args, toolchain=FakeToolchain(), execute=lambda plan: None) == 0


def test_deploy_watch_runs_as_a_script_file_outside_the_repo_root(tmp_path: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}

    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "deploy_watch.py"), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


class FakeSerial:
    """A serial port whose reads return *reads* in order: bytes, or an exception to raise."""

    def __init__(self, *reads: bytes | Exception) -> None:
        self._reads = list(reads)

    @property
    def in_waiting(self) -> int:
        pending = self._reads[0] if self._reads else b""
        return len(pending) if isinstance(pending, bytes) else 0

    def read(self, size: int = 1) -> bytes:
        if not self._reads:
            return b""
        pending = self._reads.pop(0)
        if isinstance(pending, Exception):
            raise pending
        return pending

    def close(self) -> None:
        pass


def as_serial(fake: FakeSerial) -> "Serial":
    return cast("Serial", fake)


def first_items(handle: SerialHandle, count: int, **kwargs) -> list[str | None]:
    return list(itertools.islice(iter_serial_lines(handle, **kwargs), count))


def test_iter_serial_lines_keeps_the_bytes_after_a_newline_for_the_next_line() -> None:
    handle = SerialHandle(as_serial(FakeSerial(b"first\nsec", b"ond\n")), "/dev/fake", 115200)

    assert first_items(handle, 2) == ["first", "second"]


def test_iter_serial_lines_yields_the_reconnect_marker_once_after_a_failed_read() -> None:
    reopened = FakeSerial(b"after\n")
    handle = SerialHandle(
        as_serial(FakeSerial(serial.SerialException("device disconnected"))), "/dev/fake", 115200
    )

    items = first_items(
        handle,
        2,
        reconnect_marker="soft reboot",
        reopen=lambda port, baud: as_serial(reopened),
    )

    assert items == ["soft reboot", "after"]
