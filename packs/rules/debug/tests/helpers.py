"""A SceneRun and a logger for the FPS logger's unit tests, which inject its output and clock."""

from engine.engine import GameRule
from engine.settings import Settings
from engine.state import EffectControls, GameState, SceneControls, SceneRun


class CapturingLogger:
    """Callable logger that accumulates messages for assertion in tests."""

    def __init__(self) -> None:
        self.logs: list[str] = []

    def __call__(self, message: str) -> None:
        self.logs.append(message)


def scene_run_for(rule: GameRule, settings: Settings) -> SceneRun:
    """A SceneRun dispatching to *rule* alone, its state built with *settings*."""
    return SceneRun(GameState(EffectControls(), SceneControls(), settings=settings), [rule])
