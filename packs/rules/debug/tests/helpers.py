from engine.engine import GameEngine
from engine.state import EffectControls, SceneControls


class CapturingLogger:
    """Callable logger that accumulates messages for assertion in tests."""

    def __init__(self) -> None:
        self.logs = []

    def __call__(self, message: str) -> None:
        self.logs.append(message)


class EngineFixture:
    """Pre-wired engine for rule integration tests."""

    def __init__(self):
        self.game_engine = GameEngine(EffectControls())
        self.state = self.game_engine.create_state(SceneControls())

    def update_engine(self):
        self.game_engine.update(self.state)
