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


class EffectEvent:
    """Structured lifecycle payload for effect start/stop events.

    Constructed by ``EffectManager`` for lifecycle events only.
    Renderer-triggered signals (via ``RendererConfig.notify_listeners``) are
    delivered as freeform strings and do not produce ``EffectEvent`` objects.
    """

    __slots__ = ["pack", "name", "verb"]

    def __init__(self, pack: str, name: str, verb: str) -> None:
        self.pack: str = pack
        self.name: str = name
        self.verb: str = verb

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EffectEvent):
            return NotImplemented
        return self.pack == other.pack and self.name == other.name and self.verb == other.verb

    def __hash__(self) -> int:
        return hash((self.pack, self.name, self.verb))

    def __repr__(self) -> str:
        return f"EffectEvent({self.pack!r}, {self.name!r}, {self.verb!r})"
