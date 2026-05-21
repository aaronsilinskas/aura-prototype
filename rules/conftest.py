import pytest

from engine.effects.manager import EffectControls
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event


class CapturingLogger:
    """Callable logger that accumulates messages for assertion in tests."""

    def __init__(self) -> None:
        self.logs = []

    def __call__(self, message: str) -> None:
        self.logs.append(message)


class _EventCaptureRule(GameRule):
    """Test-only rule that records every event it receives for later inspection."""

    def __init__(self):
        super().__init__("test.capture_rule", Version(1, 0))
        self.captured_events = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_events.append(event)


class EngineFixture:
    """Pre-wired engine for rule integration tests."""

    def __init__(self):
        self.game_engine = GameEngine(EffectControls())
        self._event_capture_rule = _EventCaptureRule()
        self.game_engine.add_rules(self._event_capture_rule)

    def update_engine(self):
        self.game_engine.update()

    @property
    def captured_events(self):
        return self._event_capture_rule.captured_events


@pytest.fixture
def fixture():
    fixture = EngineFixture()
    yield fixture
