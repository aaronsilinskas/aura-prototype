from effects.manager.manager import EffectManager
from effects.tests.manager.helpers import StubEffectBuilder
from engine.engine import GameEngine, GameRule, GameState, Version
from engine.events import Event, EventGroup
from engine.timer import Timer

_GROUP = EventGroup("test")


def _make_effect_manager() -> EffectManager:
    return EffectManager(builder=StubEffectBuilder(), outputs=[])


def _make_timer() -> Timer:
    return Timer()


class _CapturingRule(GameRule):
    def __init__(self) -> None:
        super().__init__("test.capturing_rule", Version(1, 0))
        self.captured_managers: list = []

    def handle_event(self, event: Event, state: GameState) -> None:
        self.captured_managers.append(state.effect_manager)


# ---------------------------------------------------------------------------
# GameState.effect_manager
# ---------------------------------------------------------------------------


def test_game_state_carries_effect_manager_from_engine() -> None:
    manager = _make_effect_manager()
    rule = _CapturingRule()
    engine = GameEngine(effect_manager=manager)
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "test"))

    engine.update(_make_timer())

    assert rule.captured_managers[0] is manager


def test_rule_can_invoke_update_on_effect_manager_via_state() -> None:
    manager = _make_effect_manager()
    timer = _make_timer()

    class _InvokingRule(GameRule):
        def __init__(self) -> None:
            super().__init__("test.invoking_rule", Version(1, 0))
            self.invoked = False

        def handle_event(self, event: Event, state: GameState) -> None:
            state.effect_manager.update(timer)
            self.invoked = True

    rule = _InvokingRule()
    engine = GameEngine(effect_manager=manager)
    engine.add_rules(rule)
    engine.queue_event(Event(_GROUP, "test"))

    engine.update(_make_timer())

    assert rule.invoked
