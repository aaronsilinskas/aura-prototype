"""Tests for device_builder's buttons subsystem and build_hardware's
cross-cutting narration spine.

Covers ``_setup_buttons`` (through build_hardware's button-pin-resolution and
button-narration coverage -- ``_setup_buttons`` has no dedicated unit tests
of its own) and ``_describe_buttons`` (the button label/pin line-formatting
helper), plus the cross-cutting slice of build_hardware's own narration: the
minimal-config unconditional-steps narration (opening banner, external
power, i2c, spi, buttons, and the closing summary, #758), the
no-logger-injected silent-no-op case, the per-button-label narration and its
resolution-failure attribution (#758), and the summary line's
outputs=/buttons= counts. Each other subsystem's own narration tests (radio,
ir, pixels, audio, haptics, accelerometer, i2c, spi) stay in that
subsystem's own split file -- test_device_builder_pixels.py (#776),
test_device_builder_buses_power.py (#777),
test_device_builder_audio_haptics.py (#778), and
test_device_builder_radio_ir.py (#779) -- this file owns only buttons and
the config-agnostic narration spine. Split out of test_device_builder.py
(#780, closing out #767) to keep that suite from growing without bound as
device_builder gains more hardware subsystems -- core, cross-subsystem
build_hardware wiring/integration tests (output ordering across multiple
components, transmit-pump identity, etc.) stay there. Config-shape helpers
(``_mock_board``, ``_neopixel_config``, ``_minimal_config``) and the
recording-logger factory (``_recording_logger``), along with the shared
ExitStack-based hardware patch helpers (``_enter_hw_patches``/
``_patch_neopixel``), all come from _hw_patch_mocks.py (#775) so every split
file imports them from one place instead of cross-importing from each
other. All hardware modules (board, busio, pulseio, digitalio) are patched
so this suite runs under CPython.
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
# build_hardware — logger spine: banner, external power, i2c, spi, buttons,
# and the closing summary line (#758)
# ---------------------------------------------------------------------------


def test_build_hardware_minimal_config_narrates_exactly_the_unconditional_steps() -> None:
    """A config with no optional sections logs exactly six lines: the opening
    banner, external power, i2c, spi, buttons, and the closing summary --
    nothing else, since pixels/accelerometer/audio/haptics/radio/ir are all
    absent and out of scope for narration in this ticket."""
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert len(lines) == 6
    assert lines[0] == "[hw] begin board=unknown-board\n"
    assert lines[1] == "[hw] external_power ok\n"
    assert lines[2] == "[hw] i2c default ok\n"
    assert lines[3] == "[hw] spi default ok\n"
    assert lines[4] == "[hw] buttons A=D9 ok\n"
    assert re.fullmatch(r"\[hw\] ready outputs=0 buttons=1 elapsed_s=\d+\.\d{3}\n", lines[5])


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
