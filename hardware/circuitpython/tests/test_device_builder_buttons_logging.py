"""Tests for device_builder's buttons subsystem (``_setup_buttons`` via
build_hardware, ``_describe_buttons``) and build_hardware's cross-cutting
narration spine (banner, i2c, spi, buttons, closing summary). Power is no
longer unconditional -- it is config-gated like every other section (#798)
-- so its narration lives with the rest of its coverage in
test_device_builder_buses_power.py. Other subsystems' narration tests live in
their own split files (pixels, buses_power, audio_haptics, radio_ir);
core/cross-subsystem build_hardware integration tests stay in
test_device_builder.py. Config-shape and logging helpers come from
_hw_patch_mocks.py (#775).
"""

from __future__ import annotations

import io
import re
from contextlib import ExitStack, redirect_stdout
from unittest.mock import MagicMock

import pytest

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _minimal_config,
    _mock_board,
    _neopixel_config,
    _patch_neopixel,
    _recording_logger,
)
from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# _describe_buttons -- pairs each button label with its declared pin name
# ---------------------------------------------------------------------------


def test_describe_buttons_pairs_each_label_with_its_declared_pin_in_order() -> None:
    from hardware.circuitpython.device_builder import _describe_buttons

    assert _describe_buttons(["GP2", "GP3", "GP4"]) == "A=GP2 B=GP3 C=GP4"


def test_describe_buttons_returns_empty_string_for_no_buttons_declared() -> None:
    from hardware.circuitpython.device_builder import _describe_buttons

    assert _describe_buttons([]) == ""


# ---------------------------------------------------------------------------
# build_hardware — logger spine: banner, i2c, spi, buttons, and the closing
# summary line (#758)
# ---------------------------------------------------------------------------


def test_build_hardware_minimal_config_narrates_exactly_the_unconditional_steps() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert len(lines) == 5
    assert lines[0] == "[hw] begin board=unknown-board\n"
    assert lines[1] == "[hw] i2c default ok\n"
    assert lines[2] == "[hw] spi default ok\n"
    assert lines[3] == "[hw] buttons A=D9 ok\n"
    assert re.fullmatch(r"\[hw\] ready outputs=0 buttons=1 elapsed_s=\d+\.\d{3}\n", lines[4])


def test_build_hardware_without_logger_injected_produces_no_output_at_all() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    captured = io.StringIO()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with redirect_stdout(captured):
            build_hardware(config, board_module=board_mock)

    assert captured.getvalue() == ""


def test_build_hardware_logs_each_button_label_and_pin() -> None:
    config = parse_device_config({"buttons": ["GP2", "GP3"]})
    board_mock = _mock_board(GP2=MagicMock(), GP3=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] buttons A=GP2 B=GP3 ok\n" in "".join(fragments)


def test_build_hardware_unknown_button_pin_marks_buttons_line_failed_not_prior_line() -> None:
    """The begin-before-_resolve_pin reorder (#758) means an unknown button
    pin name attributes its failure to the still-open buttons line, not to
    whichever line closed just before it -- proving the earlier bug (raising
    before begin() ever opened the line) is fixed."""
    config = parse_device_config({"buttons": ["NOPE"]})
    board_mock = MagicMock(spec=[])  # no attributes -> AttributeError on resolve
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] spi default ok\n"
    assert lines[-1] == "[hw] buttons A=NOPE FAILED\n"


def test_build_hardware_summary_counts_reflect_actually_built_outputs_and_buttons() -> None:
    """The summary line's outputs=/buttons= counts are read off build_hardware's
    own local state (the outputs list and resolved button pins), not off
    logging state -- this ties the counts to a config building two NeoPixel
    outputs and one button, independent of the log lines that led there."""
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    summary = "".join(fragments).splitlines()[-1]
    assert summary.startswith("[hw] ready outputs=2 buttons=1 elapsed_s=")
