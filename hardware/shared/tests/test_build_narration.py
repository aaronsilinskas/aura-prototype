"""Behaviour-driven tests for ``narrate_step`` and ``narrate_skip``."""

import pytest

from engine.log import Logger
from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.build_narration import (
    describe_accelerometer,
    describe_audio,
    describe_buttons,
    describe_haptics,
    describe_high_current_rail,
    describe_i2c,
    describe_ir,
    describe_magnetometer,
    describe_neopixel_current_budget,
    describe_pixel_entry,
    describe_radio,
    describe_sdcard,
    describe_spi,
    narrate_skip,
    narrate_step,
)
from hardware.shared.device_config import (
    AudioConfig,
    HighCurrentRailConfig,
    I2CConfig,
    I2CDeviceConfig,
    IRConfig,
    MatrixPixelsConfig,
    NeoPixelCurrentBudgetConfig,
    NeoPixelPixelsConfig,
    RadioConfig,
    SDCardConfig,
    SPIConfig,
    parse_device_config,
)


def _recording_logger(tag: str = "[hw]") -> tuple[Logger, list[str]]:
    fragments: list[str] = []
    return Logger(tag=tag, sink=fragments.append), fragments


# ---------------------------------------------------------------------------
# narrate_step — success path
# ---------------------------------------------------------------------------


def test_narrate_step_opens_and_closes_the_line_around_a_successful_build():
    logger, fragments = _recording_logger()

    narrate_step(logger, "widget", lambda: ("built", "ok"))

    assert "".join(fragments) == "[hw] widget ok\n"


def test_narrate_step_returns_the_built_value_to_the_caller():
    logger, _ = _recording_logger()

    value = narrate_step(logger, "widget", lambda: ("built-value", "ok"))

    assert value == "built-value"


def test_narrate_step_closes_with_the_builds_own_success_suffix():
    logger, fragments = _recording_logger()

    narrate_step(logger, "ir rx=A0", lambda: (object(), "writer=pio ok"))

    assert "".join(fragments) == "[hw] ir rx=A0 writer=pio ok\n"


# ---------------------------------------------------------------------------
# narrate_step — failure path
# ---------------------------------------------------------------------------


def test_narrate_step_closes_the_line_failed_when_the_build_thunk_raises():
    logger, fragments = _recording_logger()

    def _boom():
        raise ValueError("unknown pin")

    with pytest.raises(ValueError):
        narrate_step(logger, "widget", _boom)

    assert "".join(fragments) == "[hw] widget FAILED\n"


def test_narrate_step_reraises_the_build_thunks_exception_unchanged():
    logger, _ = _recording_logger()
    original = ValueError("unknown pin")

    def _boom():
        raise original

    with pytest.raises(ValueError) as excinfo:
        narrate_step(logger, "widget", _boom)

    assert excinfo.value is original


# ---------------------------------------------------------------------------
# narrate_skip — no-build path
# ---------------------------------------------------------------------------


def test_narrate_skip_emits_begin_then_end_with_no_build_step():
    logger, fragments = _recording_logger()

    narrate_skip(logger, "radio frequency=915.0", "disabled")

    assert "".join(fragments) == "[hw] radio frequency=915.0 disabled\n"


# ---------------------------------------------------------------------------
# Step descriptions — built from config pin-name strings, never resolved pins
# ---------------------------------------------------------------------------


def test_describe_high_current_rail_names_its_pin_and_polarity():
    rail = HighCurrentRailConfig(pin="D10", active_high=False)

    assert describe_high_current_rail(rail) == "high_current_rail pin=D10 active_high=False"


def test_describe_i2c_names_the_configured_scl_and_sda_pins():
    assert describe_i2c(I2CConfig(sda="GP4", scl="GP5")) == "i2c scl=GP5 sda=GP4"


def test_describe_i2c_without_a_section_names_the_board_default_pins():
    assert describe_i2c(None) == "i2c default"


def test_describe_i2c_disabled_is_the_bare_section_name():
    assert describe_i2c(I2CConfig(sda="GP4", scl="GP5", enabled=False)) == "i2c"


def test_describe_spi_names_the_configured_sck_mosi_and_miso_pins():
    spi = SPIConfig(sck="GP18", mosi="GP19", miso="GP16")

    assert describe_spi(spi) == "spi sck=GP18 mosi=GP19 miso=GP16"


def test_describe_spi_without_a_section_names_the_board_default_bus():
    assert describe_spi(None) == "spi default"


def test_describe_spi_disabled_is_the_bare_section_name():
    spi = SPIConfig(sck="GP18", mosi="GP19", miso="GP16", enabled=False)

    assert describe_spi(spi) == "spi"


def test_describe_neopixel_current_budget_reports_limit_estimate_scale_and_floor_count():
    budget = NeoPixelCurrentBudgetConfig(
        current_limit_ma=500,
        max_pixel_current_ma=60,
        min_brightness=0.1,
        estimate_ma=1234.4,
        scale=0.4051,
        at_min_brightness=1,
    )

    assert describe_neopixel_current_budget(budget) == (
        "neopixel_current_budget limit=500mA estimate=1234mA scale=0.41 at_min_brightness=1"
    )


def _pixel_entry(entry: dict[str, object]) -> MatrixPixelsConfig | NeoPixelPixelsConfig:
    return parse_device_config({"pixels": [entry]}).pixels[0]


def _matrix_entry(**overrides: object) -> dict[str, object]:
    return {
        "type": "matrix",
        "cols": 13,
        "scope_rows": {"global.main": [0, 5], "personal": [5, 9]},
        "brightness": 0.5,
        **overrides,
    }


def test_describe_pixel_entry_reports_a_matrix_entrys_cols_scope_rows_and_brightness():
    pixels = _pixel_entry(_matrix_entry())

    assert describe_pixel_entry(0, pixels) == (
        "pixels[0] matrix cols=13 scope_rows=[global.main:0-5 personal:5-9] brightness=0.50"
    )


def test_describe_pixel_entry_appends_a_matrix_entrys_configured_address():
    pixels = _pixel_entry(_matrix_entry(address=0x31))

    assert describe_pixel_entry(0, pixels).endswith(" brightness=0.50 address=0x31")


def test_describe_pixel_entry_reports_a_neopixel_strips_pin_count_order_and_segments():
    pixels = _pixel_entry(
        {
            "type": "neopixel",
            "pin": "D5",
            "count": 20,
            "scope_pixels": {"personal": [0, 10], "ambient": [10, 20]},
        }
    )

    assert describe_pixel_entry(0, pixels) == (
        "pixels[0] neopixel pin=D5 count=20 order=GRB "
        "scope_pixels=[personal:0-10 ambient:10-20] brightness=1.00"
    )


def test_describe_pixel_entry_reports_a_neopixel_strips_brightness_to_two_decimals():
    pixels = _pixel_entry(
        {
            "type": "neopixel",
            "pin": "D5",
            "count": 20,
            "brightness": 0.4,
            "scope_pixels": {"personal": [0, 20]},
        }
    )

    assert describe_pixel_entry(0, pixels).endswith(" brightness=0.40")


def test_describe_pixel_entry_joins_each_legacy_scope_strip_naming_its_scope_key():
    pixels = _pixel_entry(
        {
            "type": "neopixel",
            "scopes": {
                "personal": {"pin": "D5", "count": 10, "brightness": 0.25},
                "directional": {"pin": "D6", "count": 4, "brightness": 0.6},
            },
        }
    )

    assert describe_pixel_entry(0, pixels) == (
        "pixels[0] neopixel pin=D5 count=10 order=GRB scope=personal brightness=0.25 | "
        "pin=D6 count=4 order=GRB scope=directional brightness=0.60"
    )


def test_describe_pixel_entry_disabled_matrix_is_its_index_and_kind_only():
    pixels = _pixel_entry(_matrix_entry(enabled=False))

    assert describe_pixel_entry(1, pixels) == "pixels[1] matrix"


def test_describe_pixel_entry_disabled_neopixel_is_its_index_and_kind_only():
    pixels = _pixel_entry(
        {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}, "enabled": False}
    )

    assert describe_pixel_entry(2, pixels) == "pixels[2] neopixel"


def test_describe_buttons_pairs_each_label_with_its_declared_pin_in_order():
    assert describe_buttons(["GP2", "GP3", "GP4"]) == "buttons A=GP2 B=GP3 C=GP4"


def test_describe_buttons_with_none_declared_is_the_bare_step_name():
    assert describe_buttons([]) == "buttons"


def test_describe_accelerometer_names_its_chip():
    assert describe_accelerometer(I2CDeviceConfig()) == "accelerometer lis3dh"


def test_describe_accelerometer_appends_its_configured_address():
    accelerometer = I2CDeviceConfig(address=0x19)

    assert describe_accelerometer(accelerometer) == "accelerometer lis3dh address=0x19"


def test_describe_magnetometer_names_its_chip():
    assert describe_magnetometer(I2CDeviceConfig()) == "magnetometer mmc5603"


def test_describe_magnetometer_appends_its_configured_address():
    magnetometer = I2CDeviceConfig(address=0x30)

    assert describe_magnetometer(magnetometer) == "magnetometer mmc5603 address=0x30"


def test_describe_haptics_names_its_driver_chip():
    assert describe_haptics(I2CDeviceConfig()) == "haptics drv2605"


def test_describe_haptics_pads_its_configured_address_to_two_hex_digits():
    assert describe_haptics(I2CDeviceConfig(address=0x05)) == "haptics drv2605 address=0x05"


def _audio(**overrides: object) -> AudioConfig:
    fields = {
        "voices": 4,
        "max_volume": 0.5,
        "i2s_bit_clock": "GP10",
        "i2s_word_select": "GP11",
        "i2s_data": "GP9",
        **overrides,
    }
    return AudioConfig(**fields)


def test_describe_audio_reports_its_voices_volume_and_i2s_pins():
    assert describe_audio(_audio()) == (
        "audio voices=4 max_volume=0.50 i2s_bit_clock=GP10 i2s_word_select=GP11 i2s_data=GP9"
    )


def test_describe_audio_disabled_is_the_bare_section_name():
    assert describe_audio(_audio(enabled=False)) == "audio"


def test_describe_radio_reports_its_frequency_node_and_pins():
    radio = RadioConfig(cs="GP17", reset="GP20", frequency=915.0, node=3)

    assert describe_radio(radio) == "radio frequency=915.0 node=3 cs=GP17 reset=GP20"


def test_describe_sdcard_reports_its_mount_point_and_chip_select_pin():
    sdcard = SDCardConfig(cs="GP13", mount="/cards")

    assert describe_sdcard(sdcard) == "sdcard mount=/cards cs=GP13"


def test_describe_ir_names_a_single_rx_pin_without_multi_receiver_wording():
    ir = IRConfig(rx=["D11"], emitters={LINE: "D12"})

    assert describe_ir(ir) == "ir rx=[D11] emitters=line:D12"


def test_describe_ir_labels_two_rx_pins_as_an_ir_multi_receiver():
    ir = IRConfig(rx=["D11", "D13"], emitters={LINE: "D12"})

    assert describe_ir(ir) == "ir rx=[D11 D13] (IR multi-receiver) emitters=line:D12"


def test_describe_ir_lists_emitters_in_ir_emitters_order_not_config_order():
    ir = IRConfig(rx=["D11"], emitters={AREA_OF_EFFECT: "D14", CONE: "D13", LINE: "D12"})

    assert describe_ir(ir) == "ir rx=[D11] emitters=line:D12 cone:D13 area_of_effect:D14"


def test_describe_ir_with_no_emitters_wired_notes_none():
    assert describe_ir(IRConfig(rx=["D11"], emitters={})) == "ir rx=[D11] emitters=(none)"
