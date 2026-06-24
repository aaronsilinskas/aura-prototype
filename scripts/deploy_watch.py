"""Deploy a CircuitPython example and capture serial output until a marker or timeout.

Usage
-----
    # Deploy and watch until a marker line appears:
    python scripts/deploy_watch.py examples/effects/propmaker_demo.py --until READY

    # Deploy and watch for up to 30 seconds:
    python scripts/deploy_watch.py examples/effects/propmaker_demo.py --seconds 30

    # Both: exits 0 on match, 2 on timeout-before-match:
    python scripts/deploy_watch.py examples/effects/propmaker_demo.py --until READY --seconds 10

Exit codes
----------
    0  matched (marker found) or timed out without --until or stream ended without --until
    1  usage / port-discovery error
    2  timed out before marker matched (--until was set)
    3  soft-reboot banner never arrived within --reboot-timeout
"""

import argparse
import glob
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import IO, Final

from scripts.deploy import _DEFAULT_MOUNT, deploy

_DEFAULT_BAUD: Final = 115200
_PORT_GLOB: Final = "/dev/tty.usbmodem*"
_OPEN_RETRY_SECONDS: Final = 10.0
_OPEN_RETRY_INTERVAL: Final = 0.5
_DEFAULT_REBOOT_TIMEOUT: Final = 5.0
_CIRCUITPYTHON_BANNER: Final = "soft reboot"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class WatchResult:
    """Outcome of a watch_stream call."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason


# ---------------------------------------------------------------------------
# Core pure functions
# ---------------------------------------------------------------------------


def discard_until(
    lines: Iterable[str | None],
    marker: str,
    *,
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Consume *lines*, discarding each until one contains *marker*.

    Args:
        lines: Iterable of text lines or ``None`` on idle (no data available).
        marker: Plain substring to search for in each line.
        deadline: Absolute monotonic time after which the function gives up.
        clock: Callable returning monotonic time in seconds.

    Returns:
        ``True`` when a line containing *marker* is found before *deadline*;
        ``False`` if the deadline passes or the stream is exhausted first.
    """
    for line in lines:
        if clock() >= deadline:
            return False
        if line is not None and marker in line:
            return True
    return False


def watch_stream(
    lines: Iterable[str | None],
    *,
    until: str | None = None,
    timeout: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    out: IO[str] | None = None,
) -> WatchResult:
    """Consume *lines*, echo each to *out*, and stop on exit condition.

    Args:
        lines: Iterable of text lines or ``None`` on idle (no data available).
        until: Stop when any line contains this substring (plain substring, no
            regex). ``None`` disables marker matching.
        timeout: Maximum seconds to run. ``None`` means unlimited.
        clock: Callable returning monotonic time in seconds. Injectable for
            testing; defaults to ``time.monotonic``.
        out: Output stream for echoing lines. Defaults to ``sys.stdout``.

    Returns:
        A ``WatchResult`` whose ``reason`` is one of:
        ``"matched"`` — a line containing *until* was found;
        ``"timed_out"`` — *timeout* elapsed before a match;
        ``"stream_ended"`` — the iterable was exhausted.
    """
    if out is None:
        out = sys.stdout

    start = clock()

    for line in lines:
        if timeout is not None and clock() - start >= timeout:
            return WatchResult("timed_out")

        if line is None:
            continue

        out.write(line + "\n")

        if until is not None and until in line:
            return WatchResult("matched")

    if timeout is not None and clock() - start >= timeout:
        return WatchResult("timed_out")

    return WatchResult("stream_ended")


# ---------------------------------------------------------------------------
# Exit-code mapping
# ---------------------------------------------------------------------------


def exit_code_for(reason: str, *, until: str | None) -> int:
    """Map a WatchResult reason to a process exit code.

    Args:
        reason: The ``WatchResult.reason`` string.
        until: The ``--until`` value; ``None`` if not supplied.

    Returns:
        0 — matched, or ended/timed-out without an --until target.
        2 — timed out or stream ended before the marker was matched.
        3 — soft-reboot banner never arrived (banner_missing).
    """
    if reason == "banner_missing":
        return 3
    if reason == "matched":
        return 0
    if until is None:
        return 0
    return 2


# ---------------------------------------------------------------------------
# Port discovery
# ---------------------------------------------------------------------------


def find_port() -> str | None:
    """Auto-detect a single usbmodem serial port.

    Returns the port path when exactly one ``/dev/tty.usbmodem*`` device is
    found, otherwise ``None`` (zero or multiple matches).
    """
    matches = glob.glob(_PORT_GLOB)
    if len(matches) == 1:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# Serial adapter (thin glue — not unit tested)
# ---------------------------------------------------------------------------


def _open_serial_with_retry(
    port: str,
    baud: int,
    *,
    window: float = _OPEN_RETRY_SECONDS,
    interval: float = _OPEN_RETRY_INTERVAL,
) -> object:  # serial.Serial — typed as object to avoid a top-level pyserial import
    """Open a serial port, retrying for *window* seconds on failure.

    Returns the open ``serial.Serial`` object or raises ``OSError`` if the
    port cannot be opened within the retry window.
    """
    import serial  # type: ignore[import-untyped]

    deadline = time.monotonic() + window
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return serial.Serial(port, baud, timeout=0.1)
        except serial.SerialException as exc:
            last_exc = exc
            time.sleep(interval)
    raise OSError(f"Could not open {port} after {window}s: {last_exc}") from last_exc


def iter_serial_lines(ser: object) -> Iterable[str | None]:
    """Yield text lines from *ser*, or ``None`` when no data is available.

    Runs indefinitely; the caller (``watch_stream``) controls termination.
    """
    while True:
        raw = ser.readline()
        if raw:
            yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
        else:
            yield None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deploy a CircuitPython example and capture serial output "
            "until a marker appears or a time budget elapses."
        )
    )
    parser.add_argument(
        "example_file",
        type=Path,
        help="Example file to deploy as code.py on the device.",
    )
    parser.add_argument(
        "--mount",
        type=Path,
        default=Path(_DEFAULT_MOUNT),
        help=f"Path to the mounted CIRCUITPY volume (default: {_DEFAULT_MOUNT}).",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="Serial port (default: auto-detect from /dev/tty.usbmodem*).",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=_DEFAULT_BAUD,
        help=f"Baud rate (default: {_DEFAULT_BAUD}).",
    )
    parser.add_argument(
        "--until",
        default=None,
        metavar="TEXT",
        help="Exit 0 when a captured line contains TEXT.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        metavar="N",
        help="Bound the watch to N seconds.",
    )
    parser.add_argument(
        "--reboot-timeout",
        type=float,
        default=_DEFAULT_REBOOT_TIMEOUT,
        metavar="N",
        help=(
            f"Seconds to wait for the CircuitPython soft-reboot banner "
            f"(default: {_DEFAULT_REBOOT_TIMEOUT}). Exit 3 if it never arrives."
        ),
    )

    args = parser.parse_args()

    if args.until is None and args.seconds is None:
        parser.error("at least one of --until or --seconds is required")

    # --- port discovery ---
    port = args.port
    if port is None:
        port = find_port()
        if port is None:
            matches = glob.glob(_PORT_GLOB)
            if not matches:
                print(
                    f"Error: no serial port found matching {_PORT_GLOB}. "
                    "Connect the device or use --port.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: multiple serial ports found ({', '.join(sorted(matches))}). "
                    "Use --port to select one.",
                    file=sys.stderr,
                )
            sys.exit(1)

    try:
        ser = _open_serial_with_retry(port, args.baud)
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    with ser:
        rc = deploy(args.example_file, args.mount)
        if rc != 0:
            sys.exit(rc)

        ser.reset_input_buffer()

        banner_deadline = time.monotonic() + args.reboot_timeout
        found = discard_until(
            iter_serial_lines(ser),
            _CIRCUITPYTHON_BANNER,
            deadline=banner_deadline,
        )
        if not found:
            print(
                f"Error: soft-reboot banner not seen within {args.reboot_timeout}s. "
                "The device may have hung or missed the reload.",
                file=sys.stderr,
            )
            sys.exit(exit_code_for("banner_missing", until=args.until))

        result = watch_stream(
            iter_serial_lines(ser),
            until=args.until,
            timeout=args.seconds,
        )

    sys.exit(exit_code_for(result.reason, until=args.until))


if __name__ == "__main__":
    main()
