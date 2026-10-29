from __future__ import annotations

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from effects.effect import ResolvedClip


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
    """Structured event payload for effect lifecycle and effect-triggered signals.

    Constructed by ``EffectManager`` for lifecycle events (start/stop) and for
    effect-triggered signals (via ``EffectConfig.notify_listeners``).

    ``clip`` is the verb's ``ResolvedClip``, or ``None`` when the effect
    declares no clip for that verb. It is payload, not identity: equality,
    hashing and ``repr`` use only ``pack``, ``name`` and ``verb``.
    """

    __slots__ = ["clip", "name", "pack", "verb"]

    def __init__(self, pack: str, name: str, verb: str, clip: ResolvedClip | None = None) -> None:
        self.pack: str = pack
        self.name: str = name
        self.verb: str = verb
        self.clip: ResolvedClip | None = clip

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EffectEvent):
            return NotImplemented
        return self.pack == other.pack and self.name == other.name and self.verb == other.verb

    def __hash__(self) -> int:
        return hash((self.pack, self.name, self.verb))

    def __repr__(self) -> str:
        return f"EffectEvent({self.pack!r}, {self.name!r}, {self.verb!r})"
