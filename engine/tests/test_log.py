from engine.log import Logger, _write_nothing


def _recording_logger(tag: str = "[hw]") -> tuple[Logger, list[str]]:
    fragments: list[str] = []
    return Logger(tag=tag, sink=fragments.append), fragments


# ---------------------------------------------------------------------------
# log() — one complete tagged line
# ---------------------------------------------------------------------------


def test_log_emits_tag_and_message_as_one_complete_line():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.log("booting")

    assert "".join(fragments) == "[hw] booting\n"


# ---------------------------------------------------------------------------
# begin() / end() — open a line, then close it
# ---------------------------------------------------------------------------


def test_begin_then_end_produces_one_complete_line():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.begin("connecting")
    logger.end()

    assert "".join(fragments) == "[hw] connecting ok\n"


def test_end_uses_ok_as_the_default_suffix():
    logger, fragments = _recording_logger()

    logger.begin("step")
    logger.end()

    assert "".join(fragments).endswith(" ok\n")


def test_end_accepts_a_non_default_suffix():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.begin("uploading")
    logger.end("done")

    assert "".join(fragments) == "[hw] uploading done\n"


# ---------------------------------------------------------------------------
# Stale open-line auto-close — defensive safety net
# ---------------------------------------------------------------------------


def test_begin_while_a_line_is_open_closes_the_stale_line_with_ok_first():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.begin("first")
    logger.begin("second")
    logger.end()

    assert "".join(fragments) == "[hw] first ok\n[hw] second ok\n"


def test_log_while_a_line_is_open_closes_the_stale_line_with_ok_first():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.begin("first")
    logger.log("second")

    assert "".join(fragments) == "[hw] first ok\n[hw] second\n"


# ---------------------------------------------------------------------------
# fail() — closes an open line with FAILED, or no-ops
# ---------------------------------------------------------------------------


def test_fail_closes_an_open_line_with_failed_marker():
    logger, fragments = _recording_logger(tag="[hw]")

    logger.begin("connecting")
    logger.fail()

    assert "".join(fragments) == "[hw] connecting FAILED\n"


def test_fail_with_no_line_open_writes_nothing():
    logger, fragments = _recording_logger()

    logger.fail()

    assert fragments == []


# ---------------------------------------------------------------------------
# Logger.SILENT — shared singleton, no I/O
# ---------------------------------------------------------------------------


def test_silent_singleton_is_wired_to_the_shared_no_op_sink():
    assert Logger.SILENT._sink is _write_nothing


def test_silent_singleton_calls_do_not_raise():
    Logger.SILENT.log("message")
    Logger.SILENT.begin("message")
    Logger.SILENT.end()
    Logger.SILENT.fail()
