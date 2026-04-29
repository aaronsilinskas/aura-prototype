class EventGroup:
    __slots__ = ["name"]

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name


class Event:
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
