"""Tests for device_builder's bus/rail subsystem: ``_setup_i2c``,
``open_config_i2c``, ``_setup_spi``, ``_setup_high_current_rail``, and the
matching i2c/spi/high_current_rail slices of ``build_hardware``.

Split out of test_device_builder.py (#777) to keep that suite from growing
unbounded; other hardware subsystems stay there. Shared config-shape helpers,
``_recording_logger``, and ``_enter_hw_patches`` live in _hw_patch_mocks.py
(#775). Hardware modules (board, busio, pulseio, digitalio) are patched so
this suite runs under CPython.

The high_current_rail section replaced the old board-presence-probed
``EXTERNAL_POWER`` rail (#798): the pin is config-driven, and unlike every
other gated component a disabled high_current_rail section still drives its
pin -- to the deasserted level, holding the rail definitively off rather than
leaving it undriven.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from hardware.circuitpython.tests._hw_patch_mocks import (
    _enter_hw_patches,
    _matrix_config,
    _minimal_config,
    _mock_board,
    _recording_logger,
)
from hardware.shared.device_config import (
    parse_device_config,
)

# ---------------------------------------------------------------------------
# build_hardware's I2C bus: caller-supplied vs. self-constructed
# ---------------------------------------------------------------------------


def test_build_hardware_uses_caller_supplied_i2c_bus_for_matrix() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    supplied_i2c = MagicMock(name="caller_i2c")

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, i2c=supplied_i2c)

    mock_setup_matrix.assert_called_once_with(supplied_i2c, 1.0)


def test_build_hardware_does_not_construct_its_own_bus_when_i2c_supplied() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    supplied_i2c = MagicMock(name="caller_i2c")

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack).i2c
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, i2c=supplied_i2c)

    mock_setup_i2c.assert_not_called()


def test_build_hardware_constructs_its_own_bus_when_i2c_omitted() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack).i2c
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_i2c.assert_called_once()


def test_build_hardware_uses_its_own_constructed_bus_for_matrix_when_i2c_omitted() -> None:
    config = _matrix_config()
    board_mock = _mock_board(D9=MagicMock(), D10=MagicMock())
    own_i2c = MagicMock(name="own_i2c")

    with ExitStack() as stack:
        _enter_hw_patches(stack, own_i2c=own_i2c)
        mock_setup_matrix = stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_matrix_is31fl3741",
                return_value=MagicMock(),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_matrix.assert_called_once_with(own_i2c, 1.0)


# ---------------------------------------------------------------------------
# _setup_high_current_rail -- resolves the config-declared pin and drives the
# asserted or deasserted level, replacing the old board-presence-probed
# _setup_external_power (#798)
# ---------------------------------------------------------------------------


def _rail_config(pin: str = "GP28", active_high: bool | None = None, enabled: bool | None = None):
    rail: dict[str, object] = {"pin": pin}
    if active_high is not None:
        rail["active_high"] = active_high
    if enabled is not None:
        rail["enabled"] = enabled
    mapping = {"buttons": ["D9"], "high_current_rail": rail}
    return parse_device_config(mapping).high_current_rail


def test_setup_high_current_rail_resolves_pin_by_name() -> None:
    pin = MagicMock(name="GP28_pin")
    board_mock = _mock_board(GP28=pin)
    rail_cfg = _rail_config()

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        _setup_high_current_rail(rail_cfg, board_mock)

    mock_digitalio.DigitalInOut.assert_called_once_with(pin)


def test_setup_high_current_rail_drives_pin_high_when_active_high_and_enabled() -> None:
    board_mock = _mock_board(GP28=MagicMock())
    rail_cfg = _rail_config(active_high=True, enabled=True)

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        _setup_high_current_rail(rail_cfg, board_mock)

    mock_digitalio.DigitalInOut.return_value.switch_to_output.assert_called_once_with(value=True)


def test_setup_high_current_rail_drives_pin_low_when_active_low_and_enabled() -> None:
    board_mock = _mock_board(GP28=MagicMock())
    rail_cfg = _rail_config(active_high=False, enabled=True)

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        _setup_high_current_rail(rail_cfg, board_mock)

    mock_digitalio.DigitalInOut.return_value.switch_to_output.assert_called_once_with(value=False)


def test_setup_high_current_rail_drives_pin_low_when_active_high_and_disabled() -> None:
    """`enabled: false` still drives the pin -- to the deasserted level,
    holding the rail definitively off rather than leaving it undriven."""
    board_mock = _mock_board(GP28=MagicMock())
    rail_cfg = _rail_config(active_high=True, enabled=False)

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        _setup_high_current_rail(rail_cfg, board_mock)

    mock_digitalio.DigitalInOut.return_value.switch_to_output.assert_called_once_with(value=False)


def test_setup_high_current_rail_drives_pin_high_when_active_low_and_disabled() -> None:
    board_mock = _mock_board(GP28=MagicMock())
    rail_cfg = _rail_config(active_high=False, enabled=False)

    with ExitStack() as stack:
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        _setup_high_current_rail(rail_cfg, board_mock)

    mock_digitalio.DigitalInOut.return_value.switch_to_output.assert_called_once_with(value=True)


def test_setup_high_current_rail_bad_pin_name_raises_value_error_naming_field_and_pin() -> None:
    board_mock = MagicMock(spec=[])  # no attributes resolve
    rail_cfg = _rail_config(pin="NONEXISTENT_PIN")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import _setup_high_current_rail

        with pytest.raises(ValueError, match=r"high_current_rail\.pin.*NONEXISTENT_PIN"):
            _setup_high_current_rail(rail_cfg, board_mock)


# ---------------------------------------------------------------------------
# _setup_i2c / build_hardware handle a board with no I2C devices wired
# ---------------------------------------------------------------------------


def _i2c_config(sda: str = "GP4", scl: str = "GP5"):
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": sda, "scl": scl},
    }
    return parse_device_config(mapping).i2c


def test_setup_i2c_returns_none_when_no_pullup_found() -> None:
    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_busio.I2C.side_effect = RuntimeError(
            "No pull up found on SDA or SCL; check your wiring"
        )
        board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

        from hardware.circuitpython.device_builder import _setup_i2c

        assert _setup_i2c(None, board_mock) is None


def test_setup_i2c_uses_board_default_pins_when_no_config_present() -> None:
    """Matches pre-#679 behaviour for boards whose ``board`` module already
    aliases the bus pins."""
    board_mock = _mock_board(SCL=MagicMock(name="SCL"), SDA=MagicMock(name="SDA"))

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(None, board_mock)

    mock_busio.I2C.assert_called_once_with(board_mock.SCL, board_mock.SDA)
    assert result is mock_bus


def test_setup_i2c_resolves_named_pins_and_constructs_bus_in_scl_sda_order() -> None:
    scl_pin = MagicMock(name="scl_pin")
    sda_pin = MagicMock(name="sda_pin")
    board_mock = _mock_board(GP5=scl_pin, GP4=sda_pin)
    i2c_config = _i2c_config(sda="GP4", scl="GP5")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(i2c_config, board_mock)

    mock_busio.I2C.assert_called_once_with(scl_pin, sda_pin)
    assert result is mock_bus


def test_setup_i2c_bad_pin_name_raises_value_error() -> None:
    board_mock = MagicMock(spec=["GP5"])  # only scl resolves, sda has no attribute
    board_mock.GP5 = MagicMock(name="GP5")
    i2c_config = _i2c_config(sda="NONEXISTENT_PIN", scl="GP5")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_i2c

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            _setup_i2c(i2c_config, board_mock)


def test_setup_i2c_disabled_config_builds_no_bus() -> None:
    """``enabled: false`` on i2c builds no bus at all -- not a fall back to
    the board's default SCL/SDA pins (#692)."""
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())
    i2c_config = _i2c_config(sda="GP4", scl="GP5")
    i2c_config.enabled = False

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_i2c

        result = _setup_i2c(i2c_config, board_mock)

    assert result is None
    mock_busio.I2C.assert_not_called()


# ---------------------------------------------------------------------------
# open_config_i2c -- public bus entry point, a thin wrapper over _setup_i2c
# reachable without a full build_hardware call (#725, moved from the
# profiler-output module profiler_report, where it had drifted from
# _setup_i2c: this is _setup_i2c's own behaviour, reached publicly)
# ---------------------------------------------------------------------------


def _device_config_with_i2c(sda: str = "GP4", scl: str = "GP5"):
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": sda, "scl": scl},
    }
    return parse_device_config(mapping)


def test_open_config_i2c_resolves_named_pins_and_constructs_bus_in_scl_sda_order() -> None:
    scl_pin = MagicMock(name="scl_pin")
    sda_pin = MagicMock(name="sda_pin")
    board_mock = _mock_board(GP5=scl_pin, GP4=sda_pin)
    config = _device_config_with_i2c(sda="GP4", scl="GP5")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    mock_busio.I2C.assert_called_once_with(scl_pin, sda_pin)
    assert result is mock_bus


def test_open_config_i2c_uses_board_default_pins_when_no_config_present() -> None:
    board_mock = _mock_board(SCL=MagicMock(name="SCL"), SDA=MagicMock(name="SDA"))
    config = parse_device_config({"buttons": ["D9"]})

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    mock_busio.I2C.assert_called_once_with(board_mock.SCL, board_mock.SDA)
    assert result is mock_bus


def test_open_config_i2c_bad_pin_name_raises_field_named_value_error() -> None:
    board_mock = MagicMock(spec=["GP5"])  # only scl resolves, sda has no attribute
    board_mock.GP5 = MagicMock(name="GP5")
    config = _device_config_with_i2c(sda="NONEXISTENT_PIN", scl="GP5")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import open_config_i2c

        with pytest.raises(ValueError, match=r"i2c\.sda.*NONEXISTENT_PIN"):
            open_config_i2c(config, board_mock)


def test_open_config_i2c_disabled_section_builds_no_bus() -> None:
    """``enabled: false`` on i2c builds no bus at all, honoured the same way
    _setup_i2c honours it -- not a fall back to the board's default pins."""
    config = _device_config_with_i2c()
    config.i2c.enabled = False
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    assert result is None
    mock_busio.I2C.assert_not_called()


def test_open_config_i2c_returns_none_when_no_pullup_found() -> None:
    """A RuntimeError from busio.I2C (no pull-up wired) is caught and
    reported as None, not propagated -- open_config_i2c honours this the
    same way _setup_i2c does."""
    config = parse_device_config({"buttons": ["D9"]})
    board_mock = _mock_board(SCL=MagicMock(), SDA=MagicMock())

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_busio.I2C.side_effect = RuntimeError(
            "No pull up found on SDA or SCL; check your wiring"
        )

        from hardware.circuitpython.device_builder import open_config_i2c

        assert open_config_i2c(config, board_mock) is None


def test_open_config_i2c_never_returns_a_never_reset_stemma_bus() -> None:
    """The returned bus must be a fresh busio.I2C -- CircuitPython tears it
    down on reload -- never board.STEMMA_I2C(), which holds never_reset and
    would leave the I2C peripheral claimed for the next program on the same
    pins. This is the one behavioural fact the old profiler_report
    docstring recorded that the #725 merge into _setup_i2c had to preserve."""
    config = _device_config_with_i2c()
    board_mock = _mock_board(GP4=MagicMock(), GP5=MagicMock())
    board_mock.STEMMA_I2C = MagicMock(side_effect=AssertionError("must not call STEMMA_I2C"))

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.I2C.return_value = mock_bus

        from hardware.circuitpython.device_builder import open_config_i2c

        result = open_config_i2c(config, board_mock)

    board_mock.STEMMA_I2C.assert_not_called()
    mock_busio.I2C.assert_called_once()
    assert result is mock_bus


# ---------------------------------------------------------------------------
# _setup_spi -- the shared SPI bus radio (and future SPI peripherals) reach
# through, mirroring _setup_i2c's configured-pins-or-board-default shape
# ---------------------------------------------------------------------------


def _spi_config(sck: str = "GP2", mosi: str = "GP3", miso: str = "GP4"):
    mapping = {
        "buttons": ["D9"],
        "spi": {"sck": sck, "mosi": mosi, "miso": miso},
    }
    return parse_device_config(mapping).spi


def test_setup_spi_uses_board_default_bus_when_no_config_present() -> None:
    """Mirrors _setup_i2c's board.SCL/board.SDA fallback."""
    board_mock = _mock_board()
    own_bus = MagicMock(name="board_spi_bus")
    board_mock.SPI.return_value = own_bus

    from hardware.circuitpython.device_builder import _setup_spi

    result = _setup_spi(None, board_mock)

    board_mock.SPI.assert_called_once_with()
    assert result is own_bus


def test_setup_spi_resolves_named_pins_and_constructs_bus_in_sck_mosi_miso_order() -> None:
    sck_pin = MagicMock(name="sck_pin")
    mosi_pin = MagicMock(name="mosi_pin")
    miso_pin = MagicMock(name="miso_pin")
    board_mock = _mock_board(GP2=sck_pin, GP3=mosi_pin, GP4=miso_pin)
    spi_config = _spi_config(sck="GP2", mosi="GP3", miso="GP4")

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))
        mock_bus = MagicMock(name="bus")
        mock_busio.SPI.return_value = mock_bus

        from hardware.circuitpython.device_builder import _setup_spi

        result = _setup_spi(spi_config, board_mock)

    mock_busio.SPI.assert_called_once_with(sck_pin, MOSI=mosi_pin, MISO=miso_pin)
    assert result is mock_bus


def test_setup_spi_bad_pin_name_raises_value_error() -> None:
    board_mock = MagicMock(spec=["GP2", "GP3"])  # miso has no attribute
    spi_config = _spi_config(sck="GP2", mosi="GP3", miso="NONEXISTENT_PIN")

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_spi

        with pytest.raises(ValueError, match="NONEXISTENT_PIN"):
            _setup_spi(spi_config, board_mock)


def test_setup_spi_disabled_config_builds_no_bus() -> None:
    """``enabled: false`` on spi builds no bus at all -- not a fall back to
    board.SPI(), mirroring _setup_i2c's disabled behaviour."""
    board_mock = _mock_board()
    spi_config = _spi_config()
    spi_config.enabled = False

    with ExitStack() as stack:
        mock_busio = stack.enter_context(patch("hardware.circuitpython.device_builder.busio"))

        from hardware.circuitpython.device_builder import _setup_spi

        result = _setup_spi(spi_config, board_mock)

    assert result is None
    mock_busio.SPI.assert_not_called()
    board_mock.SPI.assert_not_called()


# ---------------------------------------------------------------------------
# build_hardware wires config.i2c and the board module into _setup_i2c
# ---------------------------------------------------------------------------


def test_build_hardware_passes_i2c_config_and_board_to_setup_i2c() -> None:
    """build_hardware threads config.i2c and the board module into the
    self-constructed-bus branch, so a bad-alias board with an i2c section
    resolves named pins rather than falling back to board.SCL/board.SDA."""
    mapping = {
        "buttons": ["D9"],
        "i2c": {"sda": "GP4", "scl": "GP5"},
    }
    config = parse_device_config(mapping)
    board_mock = _mock_board(D9=MagicMock())

    with ExitStack() as stack:
        mock_setup_i2c = _enter_hw_patches(stack).i2c

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_setup_i2c.assert_called_once_with(config.i2c, board_mock)


# ---------------------------------------------------------------------------
# build_hardware -- high_current_rail narration (#798), replacing the old
# external-power ok/no-rail line
# ---------------------------------------------------------------------------


def _config_with_rail(
    pin: str = "GP28", active_high: bool | None = None, enabled: bool | None = None
):
    rail: dict[str, object] = {"pin": pin}
    if active_high is not None:
        rail["active_high"] = active_high
    if enabled is not None:
        rail["enabled"] = enabled
    return parse_device_config({"buttons": ["D9"], "high_current_rail": rail})


def test_build_hardware_logs_rail_asserted_when_enabled() -> None:
    config = _config_with_rail(active_high=True, enabled=True)
    board_mock = _mock_board(D9=MagicMock(), GP28=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] high_current_rail pin=GP28 active_high=True asserted\n" in "".join(fragments)


def test_build_hardware_logs_rail_held_off_when_disabled() -> None:
    """`enabled: false` still resolves and drives the pin -- narrated as
    "held off", not skipped like a disabled section on every other
    component."""
    config = _config_with_rail(active_high=True, enabled=False)
    board_mock = _mock_board(D9=MagicMock(), GP28=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] high_current_rail pin=GP28 active_high=True held off\n" in "".join(fragments)


def test_build_hardware_logs_no_rail_line_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "high_current_rail" not in "".join(fragments)


def test_build_hardware_rail_bad_pin_marks_its_own_line_failed_and_propagates() -> None:
    config = _config_with_rail(pin="NONEXISTENT_PIN")
    board_mock = MagicMock(spec=["D9"])  # the rail's pin has no attribute to resolve
    board_mock.D9 = MagicMock()
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(ValueError, match=r"high_current_rail\.pin.*NONEXISTENT_PIN"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-1] == "[hw] high_current_rail pin=NONEXISTENT_PIN active_high=True FAILED\n"


def test_build_hardware_no_rail_pin_driven_when_section_absent() -> None:
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())

    with ExitStack() as stack:
        _enter_hw_patches(stack)
        mock_digitalio = stack.enter_context(
            patch("hardware.circuitpython.device_builder.digitalio")
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock)

    mock_digitalio.DigitalInOut.assert_not_called()


def test_build_hardware_logs_configured_i2c_pins() -> None:
    config = parse_device_config({"buttons": ["D9"], "i2c": {"sda": "GP4", "scl": "GP5"}})
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c scl=GP5 sda=GP4 ok\n" in "".join(fragments)


def test_build_hardware_logs_i2c_disabled_line_when_section_explicitly_disabled() -> None:
    config = parse_device_config(
        {"buttons": ["D9"], "i2c": {"sda": "GP4", "scl": "GP5", "enabled": False}}
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c disabled\n" in "".join(fragments)


def test_build_hardware_logs_i2c_no_bus_outcome_when_no_pullup_found() -> None:
    """An absent i2c section still builds a real bus on default pins -- when
    that construction finds no pull-up (busio.I2C's RuntimeError, caught
    inside _setup_i2c), the line reports "no bus", distinct from "disabled"."""
    config = _minimal_config()
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_i2c", return_value=None)
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_spi", return_value=MagicMock())
        )
        stack.enter_context(
            patch("hardware.circuitpython.device_builder._setup_buttons", return_value=MagicMock())
        )

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] i2c default no bus\n" in "".join(fragments)


def test_build_hardware_logs_configured_spi_pins() -> None:
    config = parse_device_config(
        {"buttons": ["D9"], "spi": {"sck": "GP2", "mosi": "GP3", "miso": "GP4"}}
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] spi sck=GP2 mosi=GP3 miso=GP4 ok\n" in "".join(fragments)


def test_build_hardware_logs_spi_disabled_line_when_section_explicitly_disabled() -> None:
    config = parse_device_config(
        {
            "buttons": ["D9"],
            "spi": {"sck": "GP2", "mosi": "GP3", "miso": "GP4", "enabled": False},
        }
    )
    board_mock = _mock_board(D9=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        _enter_hw_patches(stack)

        from hardware.circuitpython.device_builder import build_hardware

        build_hardware(config, board_module=board_mock, logger=logger)

    assert "[hw] spi disabled\n" in "".join(fragments)


def test_build_hardware_i2c_setup_failure_marks_i2c_line_failed_and_propagates() -> None:
    """A component that raises something other than the RuntimeError
    _setup_i2c itself catches (e.g. a wedged bus) still closes its own line
    with FAILED, and the exception still propagates -- the single
    whole-function try/except (#758), not a per-component one. A preceding
    high_current_rail section's own line must stay untouched by the later i2c
    failure."""
    config = _config_with_rail(active_high=True, enabled=True)
    board_mock = _mock_board(D9=MagicMock(), GP28=MagicMock())
    logger, fragments = _recording_logger()

    with ExitStack() as stack:
        stack.enter_context(patch("hardware.circuitpython.device_builder.digitalio"))
        stack.enter_context(
            patch(
                "hardware.circuitpython.device_builder._setup_i2c",
                side_effect=OSError("i2c bus wedged"),
            )
        )

        from hardware.circuitpython.device_builder import build_hardware

        with pytest.raises(OSError, match="i2c bus wedged"):
            build_hardware(config, board_module=board_mock, logger=logger)

    lines = "".join(fragments).splitlines(keepends=True)
    assert lines[-2] == "[hw] high_current_rail pin=GP28 active_high=True asserted\n"
    assert lines[-1] == "[hw] i2c default FAILED\n"
