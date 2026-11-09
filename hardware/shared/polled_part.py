"""PolledPart — the contract every part the tick refreshes shares. No board imports."""

__all__ = ["PolledPart"]


class PolledPart:
    """A built part the tick refreshes once per tick, after which it holds its own state.

    A plain base class (not ``typing.Protocol``, which is unavailable on the
    constrained runtimes). The **Device assembly** lists each one it builds in
    ``DeviceHardware.polled``, and the tick polls that list rather than naming
    parts. A part never reads another Polled part's state while it is polled,
    so poll order within a tick carries no meaning.
    """

    __slots__ = ()

    def update(self, elapsed: float) -> None:
        """Refresh this part's state; ``elapsed`` is the seconds since the last tick.

        Every Polled part takes ``elapsed`` so the tick can poll them alike; a
        part that keeps no time of its own ignores it.
        """
        raise NotImplementedError
