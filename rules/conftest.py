import pytest

from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event
from engine.manager.manager import EffectManager
from engine.tests.manager.helpers import StubEffectBuilder
from engine.timer import Timer


class CapturingLogger:
    def __init__(self) -> None:
        self.logs = []

    def __call__(self, message: str) -> None:
        self.logs.append(message)


class _EventCaptureRule(GameRule):
    def __init__(self):
        super().__init__("test.capture_rule", Version(1, 0))
        self.captured_events = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_events.append(event)


class EngineFixture:
    def __init__(self):
        self.timer = Timer()
        self.game_engine = GameEngine(EffectManager(builder=StubEffectBuilder(), outputs=[]))
        self._event_capture_rule = _EventCaptureRule()
        self.game_engine.add_rules(self._event_capture_rule)

    def update_engine(self):
        self.timer.update()
        self.game_engine.update(self.timer)

    @property
    def captured_events(self):
        return self._event_capture_rule.captured_events


@pytest.fixture
def fixture():
    fixture = EngineFixture()
    yield fixture
