from engine.effects.manager import EffectControls
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event, EventGroup
from engine.timer import Timer

_GROUP = EventGroup("test")


def _make_effect_controls() -> EffectControls:
    return EffectControls()


def _make_timer() -> Timer:
    return Timer()


class _CapturingRule(GameRule):
    def __init__(self) -> None:
        super().__init__("test.capturing_rule", Version(1, 0))
        self.captured_controls: list = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_controls.append(state.effect_controls)


# ---------------------------------------------------------------------------
# GameState.effect_controls
# ---------------------------------------------------------------------------


def test_game_state_carries_effect_controls_from_engine() -> None:
    controls = _make_effect_controls()
    rule = _CapturingRule()
    engine = GameEngine(effect_controls=controls)
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "test"))

    engine.update(_make_timer())

    assert rule.captured_controls[0] is controls
