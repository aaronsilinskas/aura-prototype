class EventGroup:
    """Namespace identifier for a family of related events."""

    __slots__ = ["name"]

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name


class Event:
    """Base class for all engine events.

    Subclasses add payload slots. The ``group`` and ``name`` fields together
    uniquely identify the event type for logging and debugging.
    """

    __slots__ = ["group", "name"]

    def __init__(
        self,
        group: EventGroup,
        name: str,
    ) -> None:
        self.group = group
        self.name = name

    def __str__(self) -> str:
        return f"{self.group.name}:{self.name}"
