from engine.input import ButtonData, InputEvents
from engine.state import SceneRun
from packs.rules.debug.fps_logger import FpsLoggerRule
from packs.rules.debug.tests.helpers import CapturingLogger, scene_run_for
from packs.tests.settings_helper import settings_for

_NO_BUTTONS = ButtonData(states={})
_WINDOW = 3.0


def _make_run_with_logger(start_time: float = 0.0):
    logger = CapturingLogger()
    clock_time = [start_time]
    rule = FpsLoggerRule(output=logger, clock=lambda: clock_time[0])
    run = scene_run_for(rule, settings_for(rule_packs={"debug": {"fps_logging_enabled": True}}))
    return run, logger, clock_time


def _dispatch(run: SceneRun, n: int = 1) -> None:
    for _ in range(n):
        run.state.queue_event(InputEvents.Sensors(_NO_BUTTONS))
        run.tick(0.0)


def test_no_output_by_default():
    logger = CapturingLogger()
    clock_time = [_WINDOW]
    run = scene_run_for(
        FpsLoggerRule(output=logger, clock=lambda: clock_time[0]),
        settings_for(rule_packs={"debug": {}}),
    )

    _dispatch(run, 10)

    assert logger.logs == []


def test_no_output_before_window_elapses():
    run, logger, clock_time = _make_run_with_logger()
    clock_time[0] = _WINDOW - 0.1
    _dispatch(run, 10)

    assert logger.logs == []


def test_prints_fps_after_window_elapses():
    run, logger, clock_time = _make_run_with_logger()
    _dispatch(run, 5)
    clock_time[0] = _WINDOW
    _dispatch(run)

    assert len(logger.logs) == 1
    assert logger.logs[0].startswith("FPS:")


def test_fps_value_matches_frames_per_elapsed_seconds():
    run, logger, clock_time = _make_run_with_logger()
    _dispatch(run, int(_WINDOW * 30) - 1)
    clock_time[0] = _WINDOW
    _dispatch(run)

    fps = float(logger.logs[0].split("FPS: ")[1])
    assert abs(fps - 30.0) < 0.01


def test_resets_after_printing_so_next_window_starts_fresh():
    run, logger, clock_time = _make_run_with_logger()
    _dispatch(run, 10)
    clock_time[0] = _WINDOW
    _dispatch(run)
    assert len(logger.logs) == 1

    _dispatch(run, 5)
    clock_time[0] = _WINDOW * 2
    _dispatch(run)

    assert len(logger.logs) == 2
    fps = float(logger.logs[1].split("FPS: ")[1])
    assert abs(fps - 6.0 / _WINDOW) < 0.01


def test_prints_once_per_window_not_every_frame():
    run, logger, clock_time = _make_run_with_logger()
    clock_time[0] = _WINDOW
    _dispatch(run, 20)

    assert len(logger.logs) == 1


def test_the_element_browser_turns_fps_logging_on_in_its_debug_pack_reference():
    assert settings_for("element_browser").get("debug", "fps_logging_enabled") is True
