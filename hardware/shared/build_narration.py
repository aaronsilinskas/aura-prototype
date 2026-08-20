"""Board-free "open a line, run the build, close it" narration primitive.

A component builder narrating its own construction to a :class:`~engine.log.Logger`
otherwise hand-threads the same three calls every time: ``begin`` a line describing
what it is about to build, run the build, then ``end`` the line with a success detail
or ``fail`` it on an exception. :func:`narrate_step` and :func:`narrate_skip` own that
sequence once so a component block reduces to a single call.

Imports only :class:`~engine.log.Logger` — no ``board``/``busio`` — so this module is
CPython-testable in isolation, like the rest of ``hardware/shared``.
"""

from __future__ import annotations

try:
    from collections.abc import Callable
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass  # Not available on CircuitPython

from engine.log import Logger

__all__ = ["narrate_skip", "narrate_step"]


def narrate_step(
    logger: Logger,
    description: str,
    build: Callable[[], tuple[T, str]],
) -> T:
    """Narrate one build step: open, build, close — or fail and re-raise.

    Opens *logger*'s line with *description* **before** calling *build*, so a
    failure inside *build* (e.g. resolving an unknown pin) always closes this
    step's own line rather than one already closed by a neighbouring step.
    *build* returns a ``(value, suffix)`` pair; on return, the line is closed
    with that *suffix* and *value* is returned to the caller. A plain success
    is just ``(value, "ok")`` — nothing here special-cases it. If *build*
    raises, the line is closed with ``FAILED`` and the exception is
    re-raised unchanged.

    Trusts *logger* is a real :class:`~engine.log.Logger` — a caller that
    accepts an optional logger owns normalizing ``None`` to
    :data:`~engine.log.Logger.SILENT` before calling this.
    """
    logger.begin(description)
    try:
        value, suffix = build()
    except Exception:
        logger.fail()
        raise
    logger.end(suffix)
    return value


def narrate_skip(logger: Logger, description: str, note: str) -> None:
    """Narrate a step with no build: open the line, close it with *note*.

    For a disabled or otherwise not-built component — no thunk runs.
    """
    logger.begin(description)
    logger.end(note)
