"""An engine and a logger for the FPS logger's unit tests, which inject its output and clock."""

from engine.engine import GameEngine
from engine.state import EffectControls, GameState, SceneControls


class CapturingLogger:
    """Callable logger that accumulates messages for assertion in tests."""

    def __init__(self) -> None:
        self.logs: list[str] = []

    def __call__(self, message: str) -> None:
        self.logs.append(message)


class EngineFixture:
    """Pre-wired engine for rule integration tests."""

    def __init__(self) -> None:
        self.game_engine = GameEngine(EffectControls())
        self.state: GameState = self.game_engine.create_state(SceneControls())

    def update_engine(self) -> None:
        self.game_engine.update(self.state)
