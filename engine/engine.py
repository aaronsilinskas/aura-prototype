from __future__ import annotations

from engine.effects.manager import EffectControls
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

    def handle_event(self, event: Event, state: GameState) -> None:
        # Process the event with game rules, update game state, and generate new events as needed
        pass


class GameState:
    __slots__ = ("effect_controls", "engine", "timer")

    def __init__(self, engine: GameEngine, timer: Timer, effect_controls: EffectControls) -> None:
        self.engine = engine
        self.timer = timer
        self.effect_controls = effect_controls


class GameEngine:
    __slots__ = ("_effect_controls", "_queue", "_rules")

    def __init__(self, effect_controls: EffectControls) -> None:
        self._effect_controls = effect_controls
        self._rules: list[GameRule] = []
        self._queue: list[Event] = []

    def update(self, timer: Timer) -> None:
        state = GameState(self, timer, self._effect_controls)
        while self._queue:
            event = self._queue.pop(0)
            for rule in self._rules:
                rule.handle_event(event, state)

    def queue_event(self, event: Event) -> None:
        self._queue.append(event)

    def add_rules(self, *rules: GameRule) -> None:
        self._rules.extend(rules)
