"""Tests for device_builder's radio and IR subsystems.

Covers ``_setup_radio`` (pin resolution, DigitalInOut wrapping, and
delegation to Rfm69RadioTransport) and the radio slice of ``build_hardware``
itself: config-gated wiring onto the bundle, the declared-but-no-SPI-bus and
chip-not-found hard-error cases, the disabled/undeclared-section omission
cases, and the radio narration lines (#762) -- ``logs_radio_ok_line``,
``logs_radio_disabled_line``, the no-SPI-bus and unknown-cs-pin FAILED
narration, and the absent-section silence case.

Also covers the build_hardware-level slice of IR: ``_describe_ir`` (the ir
narration line's rx/emitter detail formatting, #763), build_hardware setting
``hw.ir_receiver`` from a declared ``ir`` section, the disabled/undeclared-
section omission cases, the cone-only config-key-to-emitter mapping (#720),
the unknown rx/emitter pin hard errors, DeviceHardware's non-exposure of the
internal IR transmit gate, and the ir narration lines (#763) --
``logs_ir_ok_line_naming_rx_emitters_and_writer_kind``, the multi-receiver
wording, disabled/absent-section narration, and the unknown-pin FAILED
narration. This file does *not* get unit-level ``_setup_ir`` assembly tests
(pin/emitter wiring, codec injection, writer_factory hand-off, and
receiver-class selection by rx pin count) -- those live in test_setup_ir.py,
which already owns ``_setup_ir``'s unit-level assembly coverage.

Split out of test_device_builder.py (#779, part of #767) to keep that suite
from growing without bound as device_builder gains more hardware subsystems
-- non-radio/IR build_hardware coverage (pixels, audio, haptics,
accelerometer, i2c/spi/external-power bus setup, the general logger spine,
and the pixels-before-audio-haptic-outputs ordering test) stays there.
Config-shape helpers used by both files (``_mock_board``, ``_minimal_config``,
``_neopixel_config``, ``_recording_logger``) are imported from
test_device_builder rather than duplicated; the shared ExitStack-based
hardware patch helpers (``_enter_hw_patches``/``_patch_neopixel``) come from
_hw_patch_mocks.py (#775). All hardware modules (board, busio, pulseio,
digitalio) are patched so this suite runs under CPython.
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _patch_neopixel,
)
from hardware.circuitpython.tests.test_device_builder import (
    _minimal_config,
    _mock_board,
    _neopixel_config,
    _recording_logger,
)
from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# build_hardware -- radio is config-gated on spi, mirroring how the matrix,
# accelerometer, and haptics are config-gated on i2c (#703)
# ---------------------------------------------------------------------------


def _neopixel_config_with_radio():
    """Return a DeviceConfig with a neopixel pixels section, an spi section,
    and a radio section."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    return parse_device_config(mapping)


def test_build_hardware_radio_section_builds_radio_transport_onto_bundle() -> None:
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    mock_transport = MagicMock(name="radio_transport")

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                return_value=mock_transport,
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is mock_transport


def test_build_hardware_declared_radio_with_no_spi_bus_raises_runtime_error() -> None:
    """A declared radio whose SPI bus can't be reached is a hard error,
    mirroring the matrix-with-no-I2C-bus case -- absence must be expressed by
    omitting the section, not a silent probe failure."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder._setup_external_power"))
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock)

    mock_setup_radio.assert_not_called()


def test_build_hardware_declared_radio_raises_when_chip_not_found() -> None:
    """A declared radio whose chip can't be constructed on an available bus
    is a hard error too -- not just the no-SPI-bus case."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                side_effect=ValueError("no RFM69 found"),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="no RFM69 found"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_disabled_radio_section_omits_radio_from_bundle() -> None:
    """``radio: {enabled: false}`` is neither built nor probed, mirroring
    every other component's enabled toggle."""
    config = _neopixel_config_with_radio()
    config.radio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is None
    mocks.radio.assert_not_called()


def test_build_hardware_without_radio_section_leaves_radio_none() -> None:
    config = _neopixel_config()
    board_mock = _mock_board(D5=MagicMock(), D6=MagicMock(), D9=MagicMock())

    with ExitStack() as stack:
        mocks = _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.radio is None
    mocks.radio.assert_not_called()


# ---------------------------------------------------------------------------
# _setup_radio -- resolves radio pins and delegates to Rfm69RadioTransport
# ---------------------------------------------------------------------------


def test_setup_radio_wraps_resolved_pins_into_digitalinout_and_delegates_to_transport() -> None:
    radio_cfg = parse_device_config(
        {
            "buttons": [],
            "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 3},
        }
    ).radio
    cs_pin = MagicMock(name="cs_pin")
    reset_pin = MagicMock(name="reset_pin")
    board_mock = _mock_board(D24=cs_pin, D25=reset_pin)
    spi = MagicMock(name="spi")
    mock_transport = MagicMock(name="transport")

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )
        cs_dio = MagicMock(name="cs_dio")
        reset_dio = MagicMock(name="reset_dio")
        mock_digitalio.DigitalInOut.side_effect = [cs_dio, reset_dio]
        mock_transport_cls = stack.enter_context(
            patch(
                "hardware.circuitpython.rfm69_radio_transport.Rfm69RadioTransport",
                return_value=mock_transport,
            )
        )

        from hardware.circuitpython.device_builder import _setup_radio

        result = _setup_radio(spi, radio_cfg, board_mock)

    mock_digitalio.DigitalInOut.assert_any_call(cs_pin)
    mock_digitalio.DigitalInOut.assert_any_call(reset_pin)
    mock_transport_cls.assert_called_once_with(spi, cs_dio, reset_dio, 915.0, 3)
    assert result is mock_transport


# ---------------------------------------------------------------------------
# _describe_ir -- ir line's rx/emitter detail formatting, independent of a
# full build (#763)
# ---------------------------------------------------------------------------


def test_describe_ir_single_rx_pin_names_it_without_multi_receiver_wording() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11"], {LINE: "D12"})

    assert description == "rx=[D11] emitters=line:D12"


def test_describe_ir_two_rx_pins_names_them_as_ir_multi_receiver() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11", "D13"], {LINE: "D12"})

    assert description == "rx=[D11 D13] (IR multi-receiver) emitters=line:D12"


def test_describe_ir_lists_every_wired_emitter_in_ir_emitters_order() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    # Insertion order deliberately reversed from IR_EMITTERS (line, cone,
    # area_of_effect) to confirm the description follows the canonical
    # order, not emitter_pins' own key order -- matching _setup_ir's own
    # wiring order.
    description = _describe_ir(["D11"], {AREA_OF_EFFECT: "D14", CONE: "D13", LINE: "D12"})

    assert description == "rx=[D11] emitters=line:D12 cone:D13 area_of_effect:D14"


def test_describe_ir_no_emitters_notes_none() -> None:
    from hardware.circuitpython.device_builder import _describe_ir

    description = _describe_ir(["D11"], {})

    assert description == "rx=[D11] emitters=(none)"


# ---------------------------------------------------------------------------
# build_hardware sets hw.ir_receiver when config.ir is present
# ---------------------------------------------------------------------------


def _neopixel_config_with_ir():
    """Return a DeviceConfig with a neopixel pixels section and IR config."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {
            "rx": "D11",
            "line": "D12",
        },
    }
    return parse_device_config(mapping)


def test_build_hardware_ir_config_sets_ir_receiver() -> None:
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    mock_receiver = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({}, mock_receiver, "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is not None


def test_build_hardware_disabled_ir_section_leaves_ir_receiver_none() -> None:
    """``ir: {enabled: false}`` is neither built nor probed (#692)."""
    config = _neopixel_config_with_ir()
    config.ir.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        mock_setup_ir = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_ir")
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir_receiver is None
    mock_setup_ir.assert_not_called()


def test_build_hardware_cone_only_ir_config_wires_only_cone_transmitter() -> None:
    """A config declaring only ir.cone (no ir.line/ir.area_of_effect) wires a
    transmitter under CONE and nothing under LINE/AREA_OF_EFFECT.

    Runs the real _setup_ir (only pulseio is stubbed) so this exercises
    build_hardware's config-key-to-emitter mapping end to end — the mapping
    that previously had no direct test (#720)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11", "cone": "D13"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D13=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    wired_emitters = set(hw.transmit_pump.poll_transmits().keys())
    assert wired_emitters == {CONE}


def test_build_hardware_multi_pin_ir_rx_unknown_pin_raises_same_error_as_any_other_pin() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": ["D11", "NOPE"]}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx\[1\].*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_single_pin_ir_rx_unknown_pin_raises_unindexed_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx(?!\[).*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_unknown_ir_emitter_pin_name_raises_value_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "D11", "line": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])  # NOPE deliberately absent

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.line.*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_device_hardware_does_not_expose_the_ir_transmit_gate() -> None:
    from hardware.shared.device_hardware import DeviceHardware

    assert "gate" not in DeviceHardware.__slots__
    assert not hasattr(DeviceHardware, "ir_transmit_gate")


# ---------------------------------------------------------------------------
# build_hardware — radio narration (#762)
# ---------------------------------------------------------------------------


def test_build_hardware_logs_radio_ok_line_when_enabled_and_built() -> None:
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_radio",
                return_value=MagicMock(),
            )
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 ok\n" in "".join(fragments)


def test_build_hardware_logs_radio_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_radio()
    config.radio.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_radio_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "radio" not in "".join(fragments)


def test_build_hardware_radio_no_spi_bus_marks_its_own_line_failed_and_propagates() -> None:
    """A declared-and-enabled radio section with no SPI bus available raises via
    _require_spi -- the failure must close the radio's own open line, leaving
    the earlier spi line's own outcome (whatever it already logged) untouched
    (mirrors the accelerometer/haptics no-I2C-bus FAILED tests)."""
    config = _neopixel_config_with_radio()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=None)
        )
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_radio.assert_not_called()
    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] spi sck=SCK mosi=MOSI miso=MISO ok\n" in text
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 FAILED\n"


def test_build_hardware_radio_with_disabled_spi_marks_radio_line_failed() -> None:
    """When the spi section itself is disabled, its line already reads
    "disabled" -- an enabled radio section on top of that still raises via
    _require_spi and closes its own line with FAILED, leaving the earlier spi
    "disabled" line untouched."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO", "enabled": False},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        mock_setup_radio = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_radio")
        )
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(RuntimeError, match="radio"):
            build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_radio.assert_not_called()
    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] spi disabled\n" in text
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 FAILED\n"


def test_build_hardware_unknown_radio_cs_pin_marks_its_own_line_failed() -> None:
    """The begin-before-pin-resolution ordering means an unknown radio ``cs``
    pin name attributes FAILED to the radio line itself -- _resolve_pin runs
    inside _setup_radio, reached only after logger.begin() has already opened
    the line with the raw, unresolved cs/reset strings (mirrors #758's
    buttons case and #759's pixels case)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "radio": {"cs": "NOPE", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D5", "D9", "SCK", "MOSI", "MISO"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.SCK = MagicMock()
    board_mock.MOSI = MagicMock()
    board_mock.MISO = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack, patch_radio=False)
        _patch_neopixel(stack)
        # _setup_radio wraps each resolved pin as digitalio.DigitalInOut(...) --
        # the callee is evaluated before _resolve_pin's argument, so digitalio
        # needs a real-shaped DigitalInOut for the unknown-pin ValueError
        # (raised while evaluating that argument) to surface at all, mirroring
        # test_setup_radio_wraps_resolved_pins_into_digitalinout_and_delegates_to_transport.
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] radio frequency=915.0 node=1 cs=NOPE reset=D25 FAILED\n"


# ---------------------------------------------------------------------------
# build_hardware — ir narration (#763)
# ---------------------------------------------------------------------------


def test_build_hardware_logs_ir_ok_line_naming_rx_emitters_and_writer_kind() -> None:
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=line:D12 writer=pio ok\n" in "".join(fragments)


def test_build_hardware_logs_ir_writer_kind_matches_what_setup_ir_selected() -> None:
    """The narrated writer= value is exactly what _setup_ir's return surfaced
    -- not re-derived by build_hardware -- so swapping what _setup_ir reports
    (standing in for a writer_factory swap, per #763's own writer_kind
    hand-off tested directly in test_setup_ir.py) changes the logged kind."""
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pulseio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=line:D12 writer=pulseio ok\n" in "".join(fragments)


def test_build_hardware_logs_ir_multi_receiver_wording_for_two_rx_pins() -> None:
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": ["D11", "D13"], "line": "D12"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(
        D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock(), D13=MagicMock()
    )
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=({LINE: MagicMock()}, MagicMock(), "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11 D13] (IR multi-receiver) emitters=line:D12 writer=pio ok\n" in "".join(
        fragments
    )


def test_build_hardware_logs_ir_disabled_line_when_section_disabled() -> None:
    config = _neopixel_config_with_ir()
    config.ir.enabled = False
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        mock_setup_ir = stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_ir")
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    mock_setup_ir.assert_not_called()
    assert "[hw] ir rx=[D11] emitters=line:D12 disabled\n" in "".join(fragments)


def test_build_hardware_logs_no_ir_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "ir" not in "".join(fragments)


def test_build_hardware_unknown_ir_rx_pin_marks_its_own_line_failed_not_prior_line() -> None:
    """The begin-before-pin-resolution ordering means an unknown ir rx pin name
    attributes FAILED to the ir line itself, leaving the earlier buttons line's
    own ok outcome untouched (mirrors #758's buttons case and #762's radio
    case)."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "NOPE", "line": "D12"},
    }
    config = parse_device_config(mapping)
    # spec= so an unlisted attribute (NOPE) raises AttributeError, like a real
    # board module -- a bare MagicMock would fabricate one instead.
    board_mock = MagicMock(spec=["D5", "D9", "D12"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.D12 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    text = "".join(fragments)
    lines = text.splitlines(keepends=True)
    assert "[hw] buttons A=D9 ok\n" in text
    assert lines[-1] == "[hw] ir rx=[NOPE] emitters=line:D12 FAILED\n"


def test_build_hardware_unknown_ir_emitter_pin_marks_its_own_line_failed() -> None:
    """Same begin-before-pin-resolution attribution, for an unknown emitter
    pin name -- _resolve_pin for ir.line raises after the ir line is already
    open with the raw rx=... emitters=... detail."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11", "line": "NOPE"},
    }
    config = parse_device_config(mapping)
    # spec= so an unlisted attribute (NOPE) raises AttributeError, like a real
    # board module -- a bare MagicMock would fabricate one instead.
    board_mock = MagicMock(spec=["D5", "D9", "D11"])
    board_mock.D5 = MagicMock()
    board_mock.D9 = MagicMock()
    board_mock.D11 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match="NOPE"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] ir rx=[D11] emitters=line:NOPE FAILED\n"


def test_build_hardware_ir_rx_only_config_omits_writer_from_ok_line() -> None:
    """An ir section declaring rx but no emitters wires no transmitter, so
    _setup_ir never selects a writer -- the ok line has nothing to report and
    omits the writer= field entirely rather than printing a stale/fake kind."""
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {"rx": "D11"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(patch.dict(sys.modules, {"pulseio": MagicMock()}))

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11] emitters=(none) ok\n" in "".join(fragments)
