"""Tests for device_builder's radio and IR subsystems: ``_setup_radio`` and
the radio slice of ``build_hardware``, plus ``_describe_ir`` and the ir
slice of ``build_hardware``. Unit-level ``_setup_ir`` assembly tests
(pin/emitter wiring, codec injection, writer_factory hand-off, receiver-class
selection) live in test_setup_ir.py instead.

Split out of test_device_builder.py (#779) to keep that suite from growing
without bound; shared config-shape helpers and hardware patches come from
_hw_patch_mocks.py (#775).
"""

from __future__ import annotations

import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from engine.network import AREA_OF_EFFECT, CONE, LINE
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
# build_hardware -- radio is config-gated on spi, mirroring how the matrix,
# accelerometer, and haptics are config-gated on i2c (#703)
# ---------------------------------------------------------------------------


def _neopixel_config_with_radio():
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
        "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    }
    return parse_device_config(mapping)


def test_build_hardware_wires_setup_radio_result_onto_bundle() -> None:
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


def test_setup_radio_resolves_pins_and_wraps_the_transport_in_a_transceiver() -> None:
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
        from hardware.shared.radio_transceiver import RadioTransceiver

        result = _setup_radio(spi, radio_cfg, board_mock)

    mock_digitalio.DigitalInOut.assert_any_call(cs_pin)
    mock_digitalio.DigitalInOut.assert_any_call(reset_pin)
    mock_transport_cls.assert_called_once_with(spi, cs_dio, reset_dio, 915.0, 3)
    assert isinstance(result, RadioTransceiver)

    # The transceiver wraps exactly the constructed transport -- proven by
    # observing that send() delegates to it, mirroring how
    # test_radio_transceiver.py verifies RadioTransceiver's own delegation.
    result.send(b"\xab")
    mock_transport.send.assert_called_once_with(b"\xab")


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
# build_hardware sets hw.ir when config.ir is present
# ---------------------------------------------------------------------------


def _neopixel_config_with_ir():
    mapping = {
        "pixels": [{"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}}],
        "buttons": ["D9"],
        "ir": {
            "rx": "D11",
            "line": "D12",
        },
    }
    return parse_device_config(mapping)


def test_build_hardware_ir_config_sets_ir() -> None:
    config = _neopixel_config_with_ir()
    board_mock = _mock_board(D5=MagicMock(), D9=MagicMock(), D11=MagicMock(), D12=MagicMock())
    mock_transceiver = MagicMock()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        _patch_neopixel(stack)
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_ir",
                return_value=(mock_transceiver, "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        hw = build_hardware(config, board_module=board_mock)

    assert hw.ir is mock_transceiver


def test_build_hardware_disabled_ir_section_leaves_ir_none() -> None:
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

    assert hw.ir is None
    mock_setup_ir.assert_not_called()


def test_build_hardware_cone_only_ir_config_wires_only_cone_transmitter() -> None:
    """Runs the real _setup_ir (only pulseio is stubbed) so this exercises
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

    hw.network_controls.send_ir(b"x", CONE)  # must not raise -- CONE is wired
    with pytest.raises(ValueError):
        hw.network_controls.send_ir(b"x", LINE)  # LINE was never wired


def test_build_hardware_multi_pin_ir_rx_unknown_pin_raises_same_error_as_any_other_pin() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": ["D11", "NOPE"]}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx\[1\].*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_single_pin_ir_rx_unknown_pin_raises_unindexed_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9"])

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.rx(?!\[).*NOPE"):
            build_hardware(config, board_module=board_mock)


def test_build_hardware_unknown_ir_emitter_pin_name_raises_value_error() -> None:
    mapping = {"buttons": ["D9"], "ir": {"rx": "D11", "line": "NOPE"}}
    config = parse_device_config(mapping)
    board_mock = MagicMock(spec=["D9", "D11"])

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"ir\.line.*NOPE"):
            build_hardware(config, board_module=board_mock)


# ---------------------------------------------------------------------------
# build_hardware — radio narration (#762). One representative "ok" line plus
# the absent-section case; "disabled" is covered by the all-disabled
# comprehensive test (test_device_builder.py, #852). The no-SPI-bus FAILED
# case is proven generically by the primitive's own tests and the one
# retained integration attribution test, so only the unknown-cs-pin FAILED
# test survives here -- its ValueError isn't independently covered anywhere
# else, unlike the other components' unknown-pin cases.
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


def test_build_hardware_logs_no_radio_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "radio" not in "".join(fragments)


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
# build_hardware — ir narration (#763). One representative "ok" line plus
# the absent-section case, and the outcome variants the two comprehensive
# tests (test_device_builder.py, #852) can't reach: writer=pio vs.
# writer=pulseio, IR multi-receiver wording, and the no-emitters writer-
# omitted line. "disabled" is covered by the all-disabled comprehensive
# test; the unknown-rx/emitter-pin FAILED attribution is covered by the
# primitive's own tests, not repeated here; the underlying ValueError for
# each stays covered directly by the non-narration unknown-pin tests above.
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
                return_value=(MagicMock(), "pio"),
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
                return_value=(MagicMock(), "pulseio"),
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
                return_value=(MagicMock(), "pio"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] ir rx=[D11 D13] (IR multi-receiver) emitters=line:D12 writer=pio ok\n" in "".join(
        fragments
    )


def test_build_hardware_logs_no_ir_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "ir" not in "".join(fragments)


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
