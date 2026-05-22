from engine.input import ButtonData, InputEvents, MovementData
from packs.rules.conftest import CapturingLogger, EngineFixture
from packs.rules.debug_pack.event_logger import EventLoggerRule

_BUTTON_DATA = ButtonData(
    states={
        "A": ButtonData.UP,
        "B": ButtonData.DOWN,
        "C": ButtonData.PRESSED,
        "D": ButtonData.RELEASED,
    }
)
_MOVEMENT_DATA = MovementData(x_accel=0.0, y_accel=9.8, z_accel=0.0)


def _capture_log_entry(fixture: EngineFixture) -> str:
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger))
    fixture.state.queue_event(InputEvents.ButtonAndMovement(_BUTTON_DATA, _MOVEMENT_DATA))
    fixture.update_engine()
    return logger.logs[0]


def test_queued_event_produces_exactly_one_log_entry(fixture: EngineFixture):
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger))

    fixture.state.queue_event(InputEvents.ButtonAndMovement(_BUTTON_DATA))
    fixture.update_engine()

    assert len(logger.logs) == 1


def test_log_entry_starts_with_debug_prefix(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert log_entry.startswith("[debug]")


def test_log_entry_includes_event_name_in_uppercase(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert "IN:BUTTON_AND_MOVEMENT" in log_entry


def test_log_entry_includes_button_states(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert str(_BUTTON_DATA) in log_entry


def test_log_entry_includes_movement_data(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert str(_MOVEMENT_DATA) in log_entry


def test_log_entry_includes_elapsed_time(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert "t=" in log_entry
