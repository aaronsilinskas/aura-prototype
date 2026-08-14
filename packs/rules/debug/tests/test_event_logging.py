from engine.input import AccelerationData, ButtonData, InputEvents
from packs.rules.conftest import CapturingLogger, EngineFixture
from packs.rules.debug.event_logger import EventLoggerRule

_BUTTON_DATA = ButtonData(
    states={
        "A": ButtonData.UP,
        "B": ButtonData.DOWN,
        "C": ButtonData.PRESSED,
        "D": ButtonData.RELEASED,
    }
)
_ACCELERATION_DATA = AccelerationData(x=0.0, y=9.8, z=0.0)


def _capture_log_entry(fixture: EngineFixture) -> str:
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger))
    fixture.state.set("event_logging_enabled", True)
    fixture.state.queue_event(InputEvents.Sensors(_BUTTON_DATA, _ACCELERATION_DATA))
    fixture.update_engine()
    return logger.logs[0]


def test_no_output_by_default(fixture: EngineFixture):
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger))

    fixture.state.queue_event(InputEvents.Sensors(_BUTTON_DATA))
    fixture.update_engine()

    assert logger.logs == []


def test_queued_event_produces_exactly_one_log_entry(fixture: EngineFixture):
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger))
    fixture.state.set("event_logging_enabled", True)

    fixture.state.queue_event(InputEvents.Sensors(_BUTTON_DATA))
    fixture.update_engine()

    assert len(logger.logs) == 1


def test_log_entry_starts_with_debug_prefix(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert log_entry.startswith("[debug]")


def test_log_entry_includes_event_name_in_uppercase(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert "IN:SENSORS" in log_entry


def test_log_entry_includes_button_states(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert str(_BUTTON_DATA) in log_entry


def test_log_entry_includes_acceleration_data(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert str(_ACCELERATION_DATA) in log_entry


def test_log_entry_includes_elapsed_time(fixture: EngineFixture):
    log_entry = _capture_log_entry(fixture)

    assert "t=" in log_entry


def test_custom_enabled_key_controls_output(fixture: EngineFixture):
    logger = CapturingLogger()
    fixture.game_engine.add_rules(EventLoggerRule(output=logger, enabled_key="my_log_flag"))

    fixture.state.queue_event(InputEvents.Sensors(_BUTTON_DATA))
    fixture.update_engine()
    assert logger.logs == []

    fixture.state.set("my_log_flag", True)
    fixture.state.queue_event(InputEvents.Sensors(_BUTTON_DATA))
    fixture.update_engine()
    assert len(logger.logs) == 1
