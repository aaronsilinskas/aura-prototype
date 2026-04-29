from __future__ import annotations

from engine.events import Event
from engine.timer import Timer


class Version:
    __slots__ = ("major", "minor")

    def __init__(self, major: int, minor: int) -> None:
        self.major = major
        self.minor = minor


class GameRule:
    __slots__ = ("name", "version")

    def __init__(self, name: str, version: Version) -> None:
        self.name = name
        self.version = version

    def handle_event(self, engine: GameEngine, event: Event, timer: Timer) -> None:
        # Process the event with game rules, update game state, and generate new events as needed
        pass


class GameEngine:
    __slots__ = ("_queue", "_rules")

    def __init__(self) -> None:
        self._rules: list[GameRule] = []
        self._queue: list[Event] = []

    def update(self, timer: Timer) -> None:
        while self._queue:
            event = self._queue.pop(0)
            for rule in self._rules:
                rule.handle_event(self, event, timer)

    def queue_event(self, event: Event) -> None:
        self._queue.append(event)

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)
