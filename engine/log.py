"""Board-free, tag-prefixed line logger with an injectable sink.

Not a level-based logger: no severities, filtering, or timestamps. A line is
either emitted whole (``log``) or opened and later closed (``begin``/``end``/
``fail``) so a long-running step can report success or failure without
buffering the message until it finishes.

CircuitPython- and MicroPython-safe: no ``board`` import, and no allocation
beyond the text fragments handed to the sink.
"""

from __future__ import annotations

import sys

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass  # Not available on CircuitPython

__all__ = ["Logger"]

_DEFAULT_SUFFIX = "ok"
_FAILED_SUFFIX = "FAILED"


def _write_stdout(text: str) -> None:
    sys.stdout.write(text)


def _write_nothing(_text: str) -> None:
    pass


class Logger:
    """Writes tagged lines to an injectable sink.

    Construct with a *tag* (a marker prefix such as ``"[hw]"``) and a *sink* —
    a ``Callable[[str], None]`` that receives already-formatted text fragments
    and writes them verbatim. The logger owns every newline it emits; the sink
    appends none of its own. Defaults to writing to stdout.

    A line opened by ``begin`` stays open until ``end`` or ``fail`` closes it.
    If ``log`` or ``begin`` runs while a line is still open, the stale line is
    closed first with the default ``"ok"`` suffix — a defensive safety net,
    not a mechanism any real call path should rely on.
    """

    __slots__ = ("_open", "_sink", "_tag")

    SILENT: Final[Logger]

    def __init__(self, tag: str, sink: Callable[[str], None] = _write_stdout) -> None:
        self._tag = tag
        self._sink = sink
        self._open = False

    def log(self, message: str) -> None:
        """Emit one complete tagged line."""
        if self._open:
            self.end()
        self._sink(f"{self._tag} {message}\n")

    def begin(self, message: str) -> None:
        """Emit the tag and *message* with no terminating newline, leaving the line open."""
        if self._open:
            self.end()
        self._sink(f"{self._tag} {message}")
        self._open = True

    def end(self, suffix: str = _DEFAULT_SUFFIX) -> None:
        """Close a line opened by ``begin``, appending *suffix*.

        A no-op if no line is currently open.
        """
        if not self._open:
            return
        self._sink(f" {suffix}\n")
        self._open = False

    def fail(self) -> None:
        """Close an open line with a ``FAILED`` marker.

        A no-op if no line is currently open.
        """
        self.end(_FAILED_SUFFIX)


Logger.SILENT = Logger(tag="", sink=_write_nothing)
