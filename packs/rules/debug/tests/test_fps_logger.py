from engine.input import ButtonData, InputEvents
from packs.rules.conftest import CapturingLogger, EngineFixture
from packs.rules.debug.fps_logger import FpsLoggerRule

_NO_BUTTONS = ButtonData(states={})
_WINDOW = 3.0


def _make_fixture_with_logger(start_time: float = 0.0):
    fixture = EngineFixture()
    logger = CapturingLogger()
    clock_time = [start_time]
    rule = FpsLoggerRule(output=logger, clock=lambda: clock_time[0])
    fixture.game_engine.add_rules(rule)
    return fixture, logger, clock_time


def _dispatch(fixture: EngineFixture, n: int = 1) -> None:
    for _ in range(n):
        fixture.state.queue_event(InputEvents.ButtonAndAcceleration(_NO_BUTTONS))
        fixture.update_engine()


def test_no_output_before_window_elapses():
    fixture, logger, clock_time = _make_fixture_with_logger()
    clock_time[0] = _WINDOW - 0.1
    _dispatch(fixture, 10)

    assert logger.logs == []


def test_prints_fps_after_window_elapses():
    fixture, logger, clock_time = _make_fixture_with_logger()
    _dispatch(fixture, 5)
    clock_time[0] = _WINDOW
    _dispatch(fixture)

    assert len(logger.logs) == 1
    assert logger.logs[0].startswith("FPS:")


def test_fps_value_matches_frames_per_elapsed_seconds():
    fixture, logger, clock_time = _make_fixture_with_logger()
    _dispatch(fixture, int(_WINDOW * 30) - 1)
    clock_time[0] = _WINDOW
    _dispatch(fixture)

    fps = float(logger.logs[0].split("FPS: ")[1])
    assert abs(fps - 30.0) < 0.01


def test_resets_after_printing_so_next_window_starts_fresh():
    fixture, logger, clock_time = _make_fixture_with_logger()
    _dispatch(fixture, 10)
    clock_time[0] = _WINDOW
    _dispatch(fixture)
    assert len(logger.logs) == 1

    _dispatch(fixture, 5)
    clock_time[0] = _WINDOW * 2
    _dispatch(fixture)

    assert len(logger.logs) == 2
    fps = float(logger.logs[1].split("FPS: ")[1])
    assert abs(fps - 6.0 / _WINDOW) < 0.01


def test_prints_once_per_window_not_every_frame():
    fixture, logger, clock_time = _make_fixture_with_logger()
    clock_time[0] = _WINDOW
    _dispatch(fixture, 20)

    assert len(logger.logs) == 1


def test_no_output_when_enabled_key_is_false():
    fixture, logger, clock_time = _make_fixture_with_logger()
    fixture.state.set("fps_logging_enabled", False)
    clock_time[0] = _WINDOW
    _dispatch(fixture, 10)

    assert logger.logs == []


def test_custom_enabled_key_is_respected():
    fixture = EngineFixture()
    logger = CapturingLogger()
    clock_time = [0.0]
    rule = FpsLoggerRule(output=logger, clock=lambda: clock_time[0], enabled_key="my_fps_flag")
    fixture.game_engine.add_rules(rule)
    fixture.state.set("my_fps_flag", False)
    clock_time[0] = _WINDOW
    _dispatch(fixture, 10)

    assert logger.logs == []
