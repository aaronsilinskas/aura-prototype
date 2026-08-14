"""Behaviour-driven tests for hardware/shared/device_config.py."""

import json
from pathlib import Path

import pytest

from hardware.shared.device_config import (
    DeviceConfig,
    copy_with_enabled,
    first_neopixel_pin,
    load_device_config,
    parse_device_config,
    read_device_config_mapping,
    require_pin,
    validate_band_map,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_CONFIG_PATH = _REPO_ROOT / "examples" / "aura-device.rasppi-pico-2.json"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def matrix_config():
    return {
        "pixels": [
            {
                "type": "matrix",
                "cols": 13,
                "scope_rows": {
                    "global.buff": [0, 1],
                    "global.debuff": [1, 2],
                    "global.main": [2, 5],
                    "personal": [5, 7],
                    "directional": [7, 8],
                    "ambient": [8, 9],
                },
            }
        ],
        "buttons": ["D9", "D10"],
        "ir": {
            "rx": "D11",
            "line": "D12",
        },
        "audio": {
            "voices": 1,
            "max_volume": 0.1,
            "i2s_bit_clock": "I2S_BIT_CLOCK",
            "i2s_word_select": "I2S_WORD_SELECT",
            "i2s_data": "I2S_DATA",
        },
    }


@pytest.fixture
def neopixel_config():
    return {
        "pixels": [
            {
                "type": "neopixel",
                "scopes": {
                    "personal": {"pin": "D5", "count": 30, "order": "GRB", "brightness": 0.5},
                    "ambient": {"pin": "D6", "count": 10, "order": "RGB", "brightness": 1.0},
                },
            }
        ],
        "buttons": ["D9"],
    }


@pytest.fixture
def full_isolatable_config(matrix_config):
    # Adds every section `matrix_config` lacks (i2c, spi, radio, sdcard,
    # accelerometer, magnetometer, haptics) so every isolatable component --
    # plus both excluded buses and the excluded high-current-rail section --
    # is declared and enabled, giving `isolate` tests a config where
    # "disabled" and "absent" can never be confused for one another.
    matrix_config["i2c"] = {"sda": "GP4", "scl": "GP5"}
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": "GP8"}
    matrix_config["radio"] = {"cs": "GP13", "reset": "GP14", "frequency": 915.0, "node": 5}
    matrix_config["sdcard"] = {"cs": "GP15"}
    matrix_config["accelerometer"] = {}
    matrix_config["magnetometer"] = {}
    matrix_config["haptics"] = {}
    matrix_config["high_current_rail"] = {"pin": "GP28"}
    return matrix_config


# ---------------------------------------------------------------------------
# Happy path: full matrix config
# ---------------------------------------------------------------------------


def test_parse_full_matrix_config_maps_every_section(matrix_config):
    result = parse_device_config(matrix_config)

    assert len(result.pixels) == 1
    assert result.pixels[0].cols == 13
    assert result.buttons == ["D9", "D10"]
    assert result.ir is not None
    assert result.ir.rx == ["D11"]
    assert result.ir.emitters["line"] == "D12"
    assert result.audio is not None
    assert result.audio.voices == 1
    assert result.audio.max_volume == 0.1
    assert result.audio.i2s_bit_clock == "I2S_BIT_CLOCK"
    assert result.audio.i2s_word_select == "I2S_WORD_SELECT"
    assert result.audio.i2s_data == "I2S_DATA"


def test_parse_matrix_config_scope_rows_converted_to_ranges(matrix_config):
    result = parse_device_config(matrix_config)

    scope_rows = result.pixels[0].scope_rows
    assert scope_rows["global.buff"] == range(0, 1)
    assert scope_rows["global.main"] == range(2, 5)
    assert scope_rows["ambient"] == range(8, 9)


# ---------------------------------------------------------------------------
# read_device_config_mapping — loading from disk
# ---------------------------------------------------------------------------


def test_read_device_config_mapping_preserves_keys_the_parser_ignores(tmp_path):
    path = tmp_path / "aura-device.json"
    path.write_text(json.dumps({"buttons": ["D9"], "scene": "tag"}))

    result = read_device_config_mapping(str(path))

    assert result == {"buttons": ["D9"], "scene": "tag"}


def test_read_device_config_mapping_raises_when_file_absent(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        read_device_config_mapping(str(tmp_path / "missing.json"))


# ---------------------------------------------------------------------------
# pixels list shape: optional/empty, and duplicate matrix
# ---------------------------------------------------------------------------


def test_parse_pixels_given_as_dict_raises_value_error(matrix_config):
    matrix_config["pixels"] = matrix_config["pixels"][0]  # old single-object shape

    with pytest.raises(ValueError, match="list"):
        parse_device_config(matrix_config)


def test_parse_absent_pixels_key_yields_empty_list():
    result = parse_device_config({"buttons": ["D9"]})

    assert result.pixels == []


def test_parse_empty_pixels_list_yields_empty_list(matrix_config):
    matrix_config["pixels"] = []

    result = parse_device_config(matrix_config)

    assert result.pixels == []


def test_parse_second_matrix_entry_raises_value_error(matrix_config):
    second = dict(matrix_config["pixels"][0])
    matrix_config["pixels"].append(second)

    with pytest.raises(ValueError, match="matrix"):
        parse_device_config(matrix_config)


def test_parse_unknown_pixels_entry_type_raises_value_error_naming_entry(matrix_config):
    matrix_config["pixels"].append({"type": "led_strip"})

    with pytest.raises(ValueError, match="led_strip"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Matrix shape validation
# ---------------------------------------------------------------------------


def test_parse_matrix_without_cols_raises_value_error(matrix_config):
    del matrix_config["pixels"][0]["cols"]

    with pytest.raises(ValueError, match=r"pixels\[0\]\.cols"):
        parse_device_config(matrix_config)


def test_parse_matrix_without_scope_rows_raises_value_error(matrix_config):
    del matrix_config["pixels"][0]["scope_rows"]

    with pytest.raises(ValueError, match=r"pixels\[0\]\.scope_rows"):
        parse_device_config(matrix_config)


def test_parse_matrix_scope_rows_with_unknown_key_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["scope_rows"]["bad_scope"] = [0, 1]

    with pytest.raises(ValueError, match="bad_scope"):
        parse_device_config(matrix_config)


def test_parse_matrix_scope_rows_error_lists_valid_keys(matrix_config):
    matrix_config["pixels"][0]["scope_rows"]["bad_scope"] = [0, 1]

    with pytest.raises(ValueError, match="personal"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Matrix brightness
# ---------------------------------------------------------------------------


def test_parse_matrix_without_brightness_defaults_to_one(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.pixels[0].brightness == 1.0


def test_parse_matrix_explicit_brightness_is_stored(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 0.2

    result = parse_device_config(matrix_config)

    assert result.pixels[0].brightness == 0.2


def test_parse_matrix_brightness_boundary_zero_is_accepted(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 0.0

    result = parse_device_config(matrix_config)

    assert result.pixels[0].brightness == 0.0


def test_parse_matrix_brightness_boundary_one_is_accepted(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 1.0

    result = parse_device_config(matrix_config)

    assert result.pixels[0].brightness == 1.0


def test_parse_matrix_non_numeric_brightness_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["brightness"] = "bright"

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(matrix_config)


def test_parse_matrix_out_of_range_brightness_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 1.5

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(matrix_config)


def test_parse_matrix_negative_brightness_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["brightness"] = -0.1

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Pixels entry enabled toggle
# ---------------------------------------------------------------------------


def test_parse_matrix_pixels_absent_enabled_key_defaults_to_true(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.pixels[0].enabled is True


def test_parse_matrix_pixels_enabled_false_retains_entry_in_list(matrix_config):
    matrix_config["pixels"][0]["enabled"] = False

    result = parse_device_config(matrix_config)

    assert len(result.pixels) == 1
    assert result.pixels[0].enabled is False


def test_parse_matrix_pixels_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["pixels"][0]["enabled"] = "yes"

    with pytest.raises(ValueError, match=r"pixels\[0\]\.enabled"):
        parse_device_config(matrix_config)


def test_parse_disabled_matrix_pixels_entry_missing_cols_still_raises(matrix_config):
    matrix_config["pixels"][0]["enabled"] = False
    del matrix_config["pixels"][0]["cols"]

    with pytest.raises(ValueError, match=r"pixels\[0\]\.cols"):
        parse_device_config(matrix_config)


def test_parse_disabled_matrix_pixels_entry_overlapping_scope_rows_still_raises(matrix_config):
    matrix_config["pixels"][0]["enabled"] = False
    matrix_config["pixels"][0]["scope_rows"] = {
        "global.main": [0, 5],
        "personal": [3, 7],  # overlaps global.main at rows 3-4
    }

    with pytest.raises(ValueError, match="overlap"):
        parse_device_config(matrix_config)


def test_parse_neopixel_pixels_absent_enabled_key_defaults_to_true(neopixel_config):
    result = parse_device_config(neopixel_config)

    assert result.pixels[0].enabled is True


def test_parse_neopixel_pixels_enabled_false_retains_entry_in_list(neopixel_config):
    neopixel_config["pixels"][0]["enabled"] = False

    result = parse_device_config(neopixel_config)

    assert len(result.pixels) == 1
    assert result.pixels[0].enabled is False


def test_parse_neopixel_pixels_non_boolean_enabled_raises_value_error_naming_field(
    neopixel_config,
):
    neopixel_config["pixels"][0]["enabled"] = "yes"

    with pytest.raises(ValueError, match=r"pixels\[0\]\.enabled"):
        parse_device_config(neopixel_config)


def test_parse_disabled_neopixel_pixels_entry_reusing_pin_still_raises_value_error():
    mapping = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
                "enabled": False,
            },
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 5,
                "scope_pixels": {"directional": [0, 5]},
            },
        ],
    }

    with pytest.raises(ValueError, match=r"pin 'D5' is already used"):
        parse_device_config(mapping)


# ---------------------------------------------------------------------------
# NeoPixel legacy scope brightness validation
# ---------------------------------------------------------------------------


def test_parse_neopixel_scope_non_numeric_brightness_raises_value_error(neopixel_config):
    neopixel_config["pixels"][0]["scopes"]["personal"]["brightness"] = "bright"

    with pytest.raises(ValueError, match=r"personal\.brightness"):
        parse_device_config(neopixel_config)


def test_parse_neopixel_scope_out_of_range_brightness_raises_value_error(neopixel_config):
    neopixel_config["pixels"][0]["scopes"]["personal"]["brightness"] = 1.5

    with pytest.raises(ValueError, match=r"personal\.brightness"):
        parse_device_config(neopixel_config)


# ---------------------------------------------------------------------------
# Band-map validator: overlapping scope_rows
# ---------------------------------------------------------------------------


def test_parse_matrix_overlapping_scope_rows_raises_value_error(matrix_config):
    # Replace scope_rows with two overlapping bands.
    matrix_config["pixels"][0]["scope_rows"] = {
        "global.main": [0, 5],
        "personal": [3, 7],  # overlaps global.main at rows 3-4
    }

    with pytest.raises(ValueError, match="overlap"):
        parse_device_config(matrix_config)


def test_parse_matrix_overlapping_scope_rows_error_names_conflicting_bands(matrix_config):
    matrix_config["pixels"][0]["scope_rows"] = {
        "global.main": [0, 5],
        "personal": [3, 7],
    }

    with pytest.raises(ValueError, match=r"global\.main"):
        parse_device_config(matrix_config)


def test_validate_band_map_adjacent_bands_do_not_overlap():
    bands = {"global.main": range(0, 5), "personal": range(5, 7)}

    # Must not raise.
    validate_band_map(bands, "test")


def test_validate_band_map_overlapping_bands_raise_value_error():
    bands = {"global.main": range(0, 5), "personal": range(3, 7)}

    with pytest.raises(ValueError, match="overlap"):
        validate_band_map(bands, "test")


def test_validate_band_map_invalid_scope_key_raises_value_error():
    bands = {"bad_scope": range(0, 5)}

    with pytest.raises(ValueError, match="bad_scope"):
        validate_band_map(bands, "test")


# ---------------------------------------------------------------------------
# NeoPixel shape validation
# ---------------------------------------------------------------------------


def test_parse_neopixel_config_returns_device_config(neopixel_config):
    result = parse_device_config(neopixel_config)

    assert isinstance(result, DeviceConfig)


def test_parse_neopixel_first_entry_exposes_configured_scopes(neopixel_config):
    result = parse_device_config(neopixel_config)

    assert "personal" in result.pixels[0].scopes


def test_parse_neopixel_scope_fields_match(neopixel_config):
    result = parse_device_config(neopixel_config)

    scope = result.pixels[0].scopes["personal"]
    assert scope.pin == "D5"
    assert scope.count == 30
    assert scope.order == "GRB"
    assert scope.brightness == 0.5


def test_parse_neopixel_scope_missing_pin_raises_value_error(neopixel_config):
    del neopixel_config["pixels"][0]["scopes"]["personal"]["pin"]

    with pytest.raises(ValueError, match=r"personal\.pin"):
        parse_device_config(neopixel_config)


def test_parse_neopixel_scope_missing_count_raises_value_error(neopixel_config):
    del neopixel_config["pixels"][0]["scopes"]["personal"]["count"]

    with pytest.raises(ValueError, match=r"personal\.count"):
        parse_device_config(neopixel_config)


def test_parse_neopixel_scope_with_unknown_key_raises_value_error(neopixel_config):
    neopixel_config["pixels"][0]["scopes"]["bad_scope"] = {"pin": "D7", "count": 5}

    with pytest.raises(ValueError, match="bad_scope"):
        parse_device_config(neopixel_config)


def test_parse_neopixel_scope_error_lists_valid_keys(neopixel_config):
    neopixel_config["pixels"][0]["scopes"]["bad_scope"] = {"pin": "D7", "count": 5}

    with pytest.raises(ValueError, match="personal"):
        parse_device_config(neopixel_config)


# ---------------------------------------------------------------------------
# Unknown pixels.type
# ---------------------------------------------------------------------------


def test_parse_unknown_pixels_type_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["type"] = "led_strip"

    with pytest.raises(ValueError, match="led_strip"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Button validation: optional/empty
# ---------------------------------------------------------------------------


def test_parse_absent_buttons_key_yields_empty_list():
    result = parse_device_config({})

    assert result.buttons == []


def test_parse_empty_buttons_list_yields_empty_list(matrix_config):
    matrix_config["buttons"] = []

    result = parse_device_config(matrix_config)

    assert result.buttons == []


def test_parse_non_string_button_pin_raises_value_error(matrix_config):
    matrix_config["buttons"] = [9]

    with pytest.raises(ValueError, match=r"buttons\[0\]"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# IR validation
# ---------------------------------------------------------------------------


def test_parse_ir_without_rx_raises_value_error(matrix_config):
    del matrix_config["ir"]["rx"]

    with pytest.raises(ValueError, match=r"ir\.rx"):
        parse_device_config(matrix_config)


def test_parse_ir_without_line_omits_line_emitter(matrix_config):
    del matrix_config["ir"]["line"]

    result = parse_device_config(matrix_config)

    assert result.ir is not None
    assert "line" not in result.ir.emitters


def test_parse_ir_rx_non_string_raises_value_error(matrix_config):
    matrix_config["ir"]["rx"] = 11

    with pytest.raises(ValueError, match=r"ir\.rx"):
        parse_device_config(matrix_config)


def test_parse_ir_line_non_string_raises_value_error(matrix_config):
    matrix_config["ir"]["line"] = 12

    with pytest.raises(ValueError, match=r"ir\.line"):
        parse_device_config(matrix_config)


def test_parse_ir_unknown_emitter_key_raises_value_error(matrix_config):
    matrix_config["ir"]["laser"] = "D13"

    with pytest.raises(ValueError, match="laser"):
        parse_device_config(matrix_config)


def test_parse_ir_unknown_emitter_error_lists_valid_keys(matrix_config):
    matrix_config["ir"]["laser"] = "D13"

    with pytest.raises(ValueError, match="line"):
        parse_device_config(matrix_config)


def test_parse_absent_ir_section_yields_none(matrix_config):
    config = {"pixels": matrix_config["pixels"], "buttons": ["D9"]}

    result = parse_device_config(config)

    assert result.ir is None


def test_parse_ir_rx_list_of_pins_preserves_declared_order(matrix_config):
    matrix_config["ir"]["rx"] = ["D11", "D13", "D15"]

    result = parse_device_config(matrix_config)

    assert result.ir.rx == ["D11", "D13", "D15"]


def test_parse_ir_rx_empty_list_raises_value_error(matrix_config):
    matrix_config["ir"]["rx"] = []

    with pytest.raises(ValueError, match=r"ir\.rx"):
        parse_device_config(matrix_config)


def test_parse_ir_rx_list_with_non_string_entry_names_its_index(matrix_config):
    matrix_config["ir"]["rx"] = ["D11", 13]

    with pytest.raises(ValueError, match=r"ir\.rx\[1\]"):
        parse_device_config(matrix_config)


def test_parse_ir_absent_enabled_key_defaults_to_true(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.ir.enabled is True


def test_parse_ir_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["ir"]["enabled"] = False

    result = parse_device_config(matrix_config)

    assert result.ir is not None
    assert result.ir.enabled is False


def test_parse_ir_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["ir"]["enabled"] = "yes"

    with pytest.raises(ValueError, match=r"ir\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Accelerometer validation
# ---------------------------------------------------------------------------


def test_parse_absent_accelerometer_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.accelerometer is None


def test_parse_accelerometer_section_present_yields_non_none(matrix_config):
    matrix_config["accelerometer"] = {}

    result = parse_device_config(matrix_config)

    assert result.accelerometer is not None


def test_parse_accelerometer_unknown_key_raises_value_error_naming_field(matrix_config):
    matrix_config["accelerometer"] = {"sensitivity": "high"}

    with pytest.raises(ValueError, match=r"accelerometer\.sensitivity"):
        parse_device_config(matrix_config)


def test_parse_accelerometer_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["accelerometer"] = {}

    result = parse_device_config(matrix_config)

    assert result.accelerometer.enabled is True


def test_parse_accelerometer_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["accelerometer"] = {"enabled": False}

    result = parse_device_config(matrix_config)

    assert result.accelerometer is not None
    assert result.accelerometer.enabled is False


def test_parse_accelerometer_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["accelerometer"] = {"enabled": "yes"}

    with pytest.raises(ValueError, match=r"accelerometer\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Magnetometer validation
# ---------------------------------------------------------------------------


def test_parse_absent_magnetometer_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.magnetometer is None


def test_parse_magnetometer_section_present_yields_non_none(matrix_config):
    matrix_config["magnetometer"] = {}

    result = parse_device_config(matrix_config)

    assert result.magnetometer is not None


def test_parse_magnetometer_unknown_key_raises_value_error_naming_field(matrix_config):
    matrix_config["magnetometer"] = {"sensitivity": "high"}

    with pytest.raises(ValueError, match=r"magnetometer\.sensitivity"):
        parse_device_config(matrix_config)


def test_parse_magnetometer_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["magnetometer"] = {}

    result = parse_device_config(matrix_config)

    assert result.magnetometer.enabled is True


def test_parse_magnetometer_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["magnetometer"] = {"enabled": False}

    result = parse_device_config(matrix_config)

    assert result.magnetometer is not None
    assert result.magnetometer.enabled is False


def test_parse_magnetometer_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["magnetometer"] = {"enabled": "yes"}

    with pytest.raises(ValueError, match=r"magnetometer\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Haptics validation
# ---------------------------------------------------------------------------


def test_parse_absent_haptics_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.haptics is None


def test_parse_haptics_section_present_yields_non_none(matrix_config):
    matrix_config["haptics"] = {}

    result = parse_device_config(matrix_config)

    assert result.haptics is not None


def test_parse_haptics_unknown_key_raises_value_error_naming_field(matrix_config):
    matrix_config["haptics"] = {"intensity": 5}

    with pytest.raises(ValueError, match=r"haptics\.intensity"):
        parse_device_config(matrix_config)


def test_parse_haptics_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["haptics"] = {}

    result = parse_device_config(matrix_config)

    assert result.haptics.enabled is True


def test_parse_haptics_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["haptics"] = {"enabled": False}

    result = parse_device_config(matrix_config)

    assert result.haptics is not None
    assert result.haptics.enabled is False


def test_parse_haptics_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["haptics"] = {"enabled": "yes"}

    with pytest.raises(ValueError, match=r"haptics\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# I2C validation
# ---------------------------------------------------------------------------


def test_parse_i2c_section_maps_sda_and_scl_pins(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4", "scl": "GP5"}

    result = parse_device_config(matrix_config)

    assert result.i2c is not None
    assert result.i2c.sda == "GP4"
    assert result.i2c.scl == "GP5"


def test_parse_absent_i2c_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.i2c is None


def test_parse_i2c_missing_sda_raises_value_error_naming_field(matrix_config):
    matrix_config["i2c"] = {"scl": "GP5"}

    with pytest.raises(ValueError, match=r"i2c\.sda"):
        parse_device_config(matrix_config)


def test_parse_i2c_missing_scl_raises_value_error_naming_field(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4"}

    with pytest.raises(ValueError, match=r"i2c\.scl"):
        parse_device_config(matrix_config)


def test_parse_i2c_missing_both_pins_names_both_in_one_error(matrix_config):
    matrix_config["i2c"] = {}

    with pytest.raises(ValueError, match=r"i2c\.sda.*i2c\.scl"):
        parse_device_config(matrix_config)


def test_parse_i2c_sda_non_string_raises_value_error(matrix_config):
    matrix_config["i2c"] = {"sda": 4, "scl": "GP5"}

    with pytest.raises(ValueError, match=r"i2c\.sda must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_i2c_scl_non_string_raises_value_error(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4", "scl": 5}

    with pytest.raises(ValueError, match=r"i2c\.scl must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_i2c_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4", "scl": "GP5"}

    result = parse_device_config(matrix_config)

    assert result.i2c.enabled is True


def test_parse_i2c_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4", "scl": "GP5", "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.i2c is not None
    assert result.i2c.enabled is False


def test_parse_i2c_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["i2c"] = {"sda": "GP4", "scl": "GP5", "enabled": "yes"}

    with pytest.raises(ValueError, match=r"i2c\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# SPI validation
# ---------------------------------------------------------------------------


def test_parse_spi_section_maps_sck_mosi_miso_pins(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": "GP8"}

    result = parse_device_config(matrix_config)

    assert result.spi is not None
    assert result.spi.sck == "GP6"
    assert result.spi.mosi == "GP7"
    assert result.spi.miso == "GP8"


def test_parse_absent_spi_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.spi is None


def test_parse_spi_missing_sck_raises_value_error_naming_field(matrix_config):
    matrix_config["spi"] = {"mosi": "GP7", "miso": "GP8"}

    with pytest.raises(ValueError, match=r"spi\.sck"):
        parse_device_config(matrix_config)


def test_parse_spi_missing_mosi_raises_value_error_naming_field(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "miso": "GP8"}

    with pytest.raises(ValueError, match=r"spi\.mosi"):
        parse_device_config(matrix_config)


def test_parse_spi_missing_miso_raises_value_error_naming_field(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7"}

    with pytest.raises(ValueError, match=r"spi\.miso"):
        parse_device_config(matrix_config)


def test_parse_spi_missing_all_three_pins_names_all_in_one_error(matrix_config):
    matrix_config["spi"] = {}

    with pytest.raises(ValueError, match=r"spi\.sck.*spi\.mosi.*spi\.miso"):
        parse_device_config(matrix_config)


def test_parse_spi_sck_non_string_raises_value_error(matrix_config):
    matrix_config["spi"] = {"sck": 6, "mosi": "GP7", "miso": "GP8"}

    with pytest.raises(ValueError, match=r"spi\.sck must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_spi_mosi_non_string_raises_value_error(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": 7, "miso": "GP8"}

    with pytest.raises(ValueError, match=r"spi\.mosi must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_spi_miso_non_string_raises_value_error(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": 8}

    with pytest.raises(ValueError, match=r"spi\.miso must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_spi_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": "GP8"}

    result = parse_device_config(matrix_config)

    assert result.spi.enabled is True


def test_parse_spi_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": "GP8", "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.spi is not None
    assert result.spi.enabled is False


def test_parse_spi_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["spi"] = {"sck": "GP6", "mosi": "GP7", "miso": "GP8", "enabled": "yes"}

    with pytest.raises(ValueError, match=r"spi\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Radio validation
# ---------------------------------------------------------------------------


def test_parse_radio_section_maps_cs_reset_frequency_node(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 42}

    result = parse_device_config(matrix_config)

    assert result.radio is not None
    assert result.radio.cs == "GP9"
    assert result.radio.reset == "GP10"
    assert result.radio.frequency == 915.0
    assert result.radio.node == 42


def test_parse_absent_radio_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.radio is None


def test_parse_radio_missing_cs_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {"reset": "GP10", "frequency": 915.0, "node": 42}

    with pytest.raises(ValueError, match=r"radio\.cs"):
        parse_device_config(matrix_config)


def test_parse_radio_missing_reset_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "frequency": 915.0, "node": 42}

    with pytest.raises(ValueError, match=r"radio\.reset"):
        parse_device_config(matrix_config)


def test_parse_radio_missing_frequency_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "node": 42}

    with pytest.raises(ValueError, match=r"radio\.frequency"):
        parse_device_config(matrix_config)


def test_parse_radio_missing_node_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0}

    with pytest.raises(ValueError, match=r"radio\.node"):
        parse_device_config(matrix_config)


def test_parse_radio_cs_non_string_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": 9, "reset": "GP10", "frequency": 915.0, "node": 42}

    with pytest.raises(ValueError, match=r"radio\.cs must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_radio_reset_non_string_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": 10, "frequency": 915.0, "node": 42}

    with pytest.raises(ValueError, match=r"radio\.reset must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_radio_non_numeric_frequency_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": "915", "node": 42}

    with pytest.raises(ValueError, match=r"radio\.frequency must be a number"):
        parse_device_config(matrix_config)


def test_parse_radio_non_integer_node_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": "42"}

    with pytest.raises(ValueError, match=r"radio\.node must be an integer"):
        parse_device_config(matrix_config)


def test_parse_radio_float_node_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 42.5}

    with pytest.raises(ValueError, match=r"radio\.node must be an integer"):
        parse_device_config(matrix_config)


def test_parse_radio_negative_node_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": -1}

    with pytest.raises(ValueError, match=r"radio\.node must be in \[0, 254\]"):
        parse_device_config(matrix_config)


def test_parse_radio_node_above_254_raises_value_error(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 255}

    with pytest.raises(ValueError, match=r"radio\.node must be in \[0, 254\]"):
        parse_device_config(matrix_config)


def test_parse_radio_node_boundary_zero_is_accepted(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 0}

    result = parse_device_config(matrix_config)

    assert result.radio.node == 0


def test_parse_radio_node_boundary_254_is_accepted(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 254}

    result = parse_device_config(matrix_config)

    assert result.radio.node == 254


def test_parse_radio_unknown_key_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {
        "cs": "GP9",
        "reset": "GP10",
        "frequency": 915.0,
        "node": 42,
        "power": "high",
    }

    with pytest.raises(ValueError, match=r"radio\.power"):
        parse_device_config(matrix_config)


def test_parse_radio_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 42}

    result = parse_device_config(matrix_config)

    assert result.radio.enabled is True


def test_parse_radio_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["radio"] = {
        "cs": "GP9",
        "reset": "GP10",
        "frequency": 915.0,
        "node": 42,
        "enabled": False,
    }

    result = parse_device_config(matrix_config)

    assert result.radio is not None
    assert result.radio.enabled is False


def test_parse_radio_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["radio"] = {
        "cs": "GP9",
        "reset": "GP10",
        "frequency": 915.0,
        "node": 42,
        "enabled": "yes",
    }

    with pytest.raises(ValueError, match=r"radio\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# SD card validation
# ---------------------------------------------------------------------------


def test_parse_sdcard_section_maps_cs_mount_and_enabled(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "mount": "/data", "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.sdcard is not None
    assert result.sdcard.cs == "GP9"
    assert result.sdcard.mount == "/data"
    assert result.sdcard.enabled is False


def test_parse_sdcard_without_mount_defaults_to_slash_sd(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9"}

    result = parse_device_config(matrix_config)

    assert result.sdcard.mount == "/sd"


def test_parse_absent_sdcard_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.sdcard is None


def test_parse_sdcard_missing_cs_raises_value_error_naming_field(matrix_config):
    matrix_config["sdcard"] = {}

    with pytest.raises(ValueError, match=r"sdcard\.cs"):
        parse_device_config(matrix_config)


def test_parse_sdcard_cs_non_string_raises_value_error(matrix_config):
    matrix_config["sdcard"] = {"cs": 9}

    with pytest.raises(ValueError, match=r"sdcard\.cs must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_sdcard_non_string_mount_raises_value_error_naming_field(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "mount": 5}

    with pytest.raises(ValueError, match=r"sdcard\.mount"):
        parse_device_config(matrix_config)


def test_parse_sdcard_mount_without_leading_slash_raises_value_error_naming_field(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "mount": "data"}

    with pytest.raises(ValueError, match=r"sdcard\.mount"):
        parse_device_config(matrix_config)


def test_parse_sdcard_empty_mount_raises_value_error_naming_field(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "mount": ""}

    with pytest.raises(ValueError, match=r"sdcard\.mount"):
        parse_device_config(matrix_config)


def test_parse_sdcard_unknown_key_raises_value_error_naming_allowed_keys(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "speed": "fast"}

    with pytest.raises(ValueError, match=r"sdcard\.speed.*cs, mount, enabled"):
        parse_device_config(matrix_config)


def test_parse_sdcard_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9"}

    result = parse_device_config(matrix_config)

    assert result.sdcard.enabled is True


def test_parse_sdcard_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.sdcard is not None
    assert result.sdcard.enabled is False


def test_parse_sdcard_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "enabled": "yes"}

    with pytest.raises(ValueError, match=r"sdcard\.enabled"):
        parse_device_config(matrix_config)


def test_parse_sdcard_enabled_false_missing_cs_still_raises_value_error(matrix_config):
    matrix_config["sdcard"] = {"enabled": False}

    with pytest.raises(ValueError, match=r"sdcard\.cs"):
        parse_device_config(matrix_config)


def test_parse_sdcard_enabled_false_invalid_mount_still_raises_value_error(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9", "mount": "data", "enabled": False}

    with pytest.raises(ValueError, match=r"sdcard\.mount"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# High-current rail (enable pin) validation
# ---------------------------------------------------------------------------


def test_parse_high_current_rail_section_maps_pin_active_high_and_enabled(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "active_high": False, "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.high_current_rail is not None
    assert result.high_current_rail.pin == "GP28"
    assert result.high_current_rail.active_high is False
    assert result.high_current_rail.enabled is False


def test_parse_absent_high_current_rail_section_yields_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.high_current_rail is None


def test_parse_high_current_rail_missing_pin_raises_value_error_naming_field(matrix_config):
    matrix_config["high_current_rail"] = {}

    with pytest.raises(ValueError, match=r"high_current_rail\.pin"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_non_string_pin_raises_value_error_naming_field(matrix_config):
    matrix_config["high_current_rail"] = {"pin": 28}

    with pytest.raises(ValueError, match=r"high_current_rail\.pin must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_absent_active_high_key_defaults_to_true(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28"}

    result = parse_device_config(matrix_config)

    assert result.high_current_rail.active_high is True


def test_parse_high_current_rail_non_boolean_active_high_raises_value_error(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "active_high": "yes"}

    with pytest.raises(ValueError, match=r"high_current_rail\.active_high"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28"}

    result = parse_device_config(matrix_config)

    assert result.high_current_rail.enabled is True


def test_parse_high_current_rail_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "enabled": False}

    result = parse_device_config(matrix_config)

    assert result.high_current_rail is not None
    assert result.high_current_rail.enabled is False


def test_parse_high_current_rail_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "enabled": "yes"}

    with pytest.raises(ValueError, match=r"high_current_rail\.enabled"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_enabled_false_missing_pin_still_raises_value_error(matrix_config):
    matrix_config["high_current_rail"] = {"enabled": False}

    with pytest.raises(ValueError, match=r"high_current_rail\.pin"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_unknown_key_raises_value_error_naming_allowed_keys(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "speed": "fast"}

    with pytest.raises(ValueError, match=r"high_current_rail\.speed.*pin, active_high, enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Audio validation
# ---------------------------------------------------------------------------


def test_parse_audio_bad_voice_count_raises_value_error(matrix_config):
    matrix_config["audio"]["voices"] = 0

    with pytest.raises(ValueError, match=r"audio\.voices"):
        parse_device_config(matrix_config)


def test_parse_audio_non_integer_voices_raises_value_error(matrix_config):
    matrix_config["audio"]["voices"] = "one"

    with pytest.raises(ValueError, match=r"audio\.voices"):
        parse_device_config(matrix_config)


def test_parse_audio_section_with_no_clips_key_succeeds_and_carries_no_clips_attribute(
    matrix_config,
):
    """AudioConfig no longer carries a clips map (#804) -- clip resolution moved
    to AudioRegistry -- so a clips-free audio section parses with
    voices/max_volume/I2S validation unaffected."""
    result = parse_device_config(matrix_config)

    assert result.audio is not None
    assert result.audio.voices == 1
    assert result.audio.max_volume == 0.1
    assert result.audio.i2s_bit_clock == "I2S_BIT_CLOCK"
    assert not hasattr(result.audio, "clips")


def test_parse_absent_audio_section_yields_none(matrix_config):
    config = {"pixels": matrix_config["pixels"], "buttons": ["D9"]}

    result = parse_device_config(config)

    assert result.audio is None


def test_parse_audio_absent_enabled_key_defaults_to_true(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.audio.enabled is True


def test_parse_audio_enabled_false_retains_object_not_none(matrix_config):
    matrix_config["audio"]["enabled"] = False

    result = parse_device_config(matrix_config)

    assert result.audio is not None
    assert result.audio.enabled is False


def test_parse_audio_non_boolean_enabled_raises_value_error_naming_field(matrix_config):
    matrix_config["audio"]["enabled"] = "yes"

    with pytest.raises(ValueError, match=r"audio\.enabled"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Audio I2S pin validation — required-together, single error naming all
# missing fields, and string-type guards.
# ---------------------------------------------------------------------------


def test_parse_audio_missing_one_i2s_pin_raises_value_error(matrix_config):
    del matrix_config["audio"]["i2s_data"]

    with pytest.raises(ValueError, match=r"audio\.i2s_data"):
        parse_device_config(matrix_config)


def test_parse_audio_missing_two_i2s_pins_names_both_in_one_error(matrix_config):
    del matrix_config["audio"]["i2s_word_select"]
    del matrix_config["audio"]["i2s_data"]

    with pytest.raises(ValueError, match=r"audio\.i2s_word_select.*audio\.i2s_data"):
        parse_device_config(matrix_config)


def test_parse_audio_missing_all_i2s_pins_names_all_three_in_one_error(matrix_config):
    del matrix_config["audio"]["i2s_bit_clock"]
    del matrix_config["audio"]["i2s_word_select"]
    del matrix_config["audio"]["i2s_data"]

    with pytest.raises(
        ValueError, match=r"audio\.i2s_bit_clock.*audio\.i2s_word_select.*audio\.i2s_data"
    ):
        parse_device_config(matrix_config)


def test_parse_audio_i2s_bit_clock_non_string_raises_value_error(matrix_config):
    matrix_config["audio"]["i2s_bit_clock"] = 11

    with pytest.raises(ValueError, match=r"audio\.i2s_bit_clock must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_audio_i2s_word_select_non_string_raises_value_error(matrix_config):
    matrix_config["audio"]["i2s_word_select"] = 12

    with pytest.raises(ValueError, match=r"audio\.i2s_word_select must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_audio_i2s_data_non_string_raises_value_error(matrix_config):
    matrix_config["audio"]["i2s_data"] = 13

    with pytest.raises(ValueError, match=r"audio\.i2s_data must be a string pin name"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Committed sample config — examples/aura-device.rasppi-pico-2.json parses as-is
# ---------------------------------------------------------------------------


def test_committed_sample_device_config_parses():
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    result = parse_device_config(mapping)

    assert result.audio is not None
    assert result.audio.i2s_bit_clock == "GP7"
    assert result.audio.i2s_word_select == "GP8"
    assert result.audio.i2s_data == "GP6"
    assert result.accelerometer is not None
    assert result.haptics is not None
    assert result.spi is not None
    assert result.radio is not None


def test_committed_sample_device_config_carries_no_clips_map():
    """hardware_test's sfx_test clip now resolves via AudioRegistry's
    hardware_test/sounds/sfx_test_start.wav scene overlay (#804), not a
    device-config clips map."""
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    assert "clips" not in mapping["audio"]


# ---------------------------------------------------------------------------
# require_pin — narrow catch surfacing a uniform "not declared" ValueError
# ---------------------------------------------------------------------------


def test_require_pin_returns_configured_value_when_field_present(matrix_config):
    config = parse_device_config(matrix_config)

    result = require_pin(config, lambda c: c.ir.emitters["line"], "ir.line")

    assert result == "D12"


def test_require_pin_raises_value_error_naming_field_label_on_missing_section(matrix_config):
    del matrix_config["ir"]
    config = parse_device_config(matrix_config)

    with pytest.raises(ValueError, match=r"ir\.line not declared in aura-device\.json"):
        require_pin(config, lambda c: c.ir.emitters["line"], "ir.line")


def test_require_pin_raises_value_error_naming_field_label_on_missing_dict_key(matrix_config):
    config = parse_device_config(matrix_config)

    with pytest.raises(ValueError, match=r"ir\.cone not declared in aura-device\.json"):
        require_pin(config, lambda c: c.ir.emitters["cone"], "ir.cone")


def test_require_pin_raises_value_error_naming_field_label_on_missing_list_index(matrix_config):
    config = parse_device_config(matrix_config)

    with pytest.raises(ValueError, match=r"buttons\[5\] not declared in aura-device\.json"):
        require_pin(config, lambda c: c.buttons[5], "buttons[5]")


def test_require_pin_does_not_swallow_unrelated_getter_exception(matrix_config):
    config = parse_device_config(matrix_config)

    def _broken_getter(_config):
        raise TypeError("bug inside getter")

    with pytest.raises(TypeError, match="bug inside getter"):
        require_pin(config, _broken_getter, "ir.line")


# ---------------------------------------------------------------------------
# first_neopixel_pin — modern strips shape wins over legacy scopes
# ---------------------------------------------------------------------------


def test_first_neopixel_pin_returns_pin_from_strips_entry():
    config = parse_device_config(
        {
            "pixels": [
                {
                    "type": "neopixel",
                    "pin": "D5",
                    "count": 30,
                    "scope_pixels": {"personal": [0, 10]},
                }
            ],
            "buttons": ["D9"],
        }
    )

    assert first_neopixel_pin(config) == "D5"


def test_first_neopixel_pin_returns_pin_from_legacy_scopes_entry(neopixel_config):
    config = parse_device_config(neopixel_config)

    assert first_neopixel_pin(config) == "D5"


def test_first_neopixel_pin_raises_key_error_for_matrix_only_config(matrix_config):
    config = parse_device_config(matrix_config)

    with pytest.raises(KeyError):
        first_neopixel_pin(config)


def test_first_neopixel_pin_composes_with_require_pin_for_uniform_message(matrix_config):
    config = parse_device_config(matrix_config)

    with pytest.raises(ValueError, match=r"neopixel\.pin not declared in aura-device\.json"):
        require_pin(config, first_neopixel_pin, "neopixel.pin")


# ---------------------------------------------------------------------------
# load_device_config — board-free parse-and-load pair
# ---------------------------------------------------------------------------


def test_load_device_config_parses_valid_file(tmp_path, matrix_config):
    path = tmp_path / "aura-device.json"
    path.write_text(json.dumps(matrix_config))

    result = load_device_config(str(path))

    assert isinstance(result, DeviceConfig)
    assert result.buttons == ["D9", "D10"]


def test_load_device_config_raises_when_file_missing(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        load_device_config(str(tmp_path / "missing.json"))


# ---------------------------------------------------------------------------
# copy_with_enabled — the single copy primitive (isolate's _disabled_copy,
# generalized to force either direction; moved from profiler_report, #725)
# ---------------------------------------------------------------------------


def test_copy_with_enabled_returns_a_distinct_instance_with_enabled_forced():
    config = parse_device_config({"haptics": {}})

    copy = copy_with_enabled(config.haptics, enabled=False)

    assert copy is not config.haptics
    assert copy.enabled is False
    assert config.haptics.enabled is True


def test_copy_with_enabled_can_force_enabled_true_on_a_declared_disabled_section():
    config = parse_device_config({"haptics": {"enabled": False}})

    copy = copy_with_enabled(config.haptics, enabled=True)

    assert copy.enabled is True
    assert config.haptics.enabled is False


def test_copy_with_enabled_preserves_every_other_field_of_a_pixels_entry():
    config = parse_device_config(
        {
            "pixels": [
                {
                    "type": "matrix",
                    "cols": 13,
                    "scope_rows": {"personal": [0, 9]},
                    "brightness": 0.5,
                }
            ]
        }
    )
    original = config.pixels[0]

    copy = copy_with_enabled(original, enabled=False)

    assert copy.cols == original.cols
    assert copy.scope_rows == original.scope_rows
    assert copy.brightness == original.brightness
    assert copy.enabled is False


def test_copy_with_enabled_shares_mutable_slot_values_with_the_original():
    # The copy is shallow -- a mutable slot (scope_rows) is the *same* dict
    # object on both, not a deep copy of it.
    config = parse_device_config(
        {
            "pixels": [
                {
                    "type": "matrix",
                    "cols": 13,
                    "scope_rows": {"personal": [0, 9]},
                }
            ]
        }
    )
    original = config.pixels[0]

    copy = copy_with_enabled(original, enabled=False)

    assert copy.scope_rows is original.scope_rows


# ---------------------------------------------------------------------------
# DeviceConfig.isolate — derived, non-reparsing single-component isolation
# ---------------------------------------------------------------------------


def test_isolate_returns_a_new_device_config_distinct_from_the_original(full_isolatable_config):
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep="audio")

    assert isinstance(isolated, DeviceConfig)
    assert isolated is not config


def test_isolate_leaves_the_original_config_unchanged(full_isolatable_config):
    config = parse_device_config(full_isolatable_config)

    config.isolate(keep="audio")

    assert config.ir.enabled is True
    assert config.accelerometer.enabled is True
    assert config.magnetometer.enabled is True
    assert config.haptics.enabled is True
    assert config.radio.enabled is True
    assert config.sdcard.enabled is True
    assert config.high_current_rail.enabled is True
    assert all(entry.enabled for entry in config.pixels)


_ISOLATABLE_COMPONENTS = (
    "pixels",
    "audio",
    "ir",
    "accelerometer",
    "magnetometer",
    "haptics",
    "radio",
    "sdcard",
)


@pytest.mark.parametrize("keep", _ISOLATABLE_COMPONENTS)
def test_isolate_leaves_kept_component_declared_and_disables_the_other_five(
    full_isolatable_config, keep
):
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep=keep)

    for name in _ISOLATABLE_COMPONENTS:
        value = getattr(isolated, name)
        expect_enabled = name == keep
        if name == "pixels":
            assert value, "pixels section must be retained, not dropped"
            assert all(entry.enabled is expect_enabled for entry in value)
        else:
            assert value is not None, f"{name} section must be retained, not None"
            assert value.enabled is expect_enabled


def test_isolate_does_not_force_enable_a_kept_component_declared_disabled(full_isolatable_config):
    full_isolatable_config["audio"]["enabled"] = False
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep="audio")

    assert isolated.audio.enabled is False


@pytest.mark.parametrize("keep", _ISOLATABLE_COMPONENTS)
def test_isolate_never_touches_i2c_spi_buttons_or_high_current_rail(full_isolatable_config, keep):
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep=keep)

    assert isolated.i2c.sda == config.i2c.sda
    assert isolated.i2c.scl == config.i2c.scl
    assert isolated.i2c.enabled == config.i2c.enabled
    assert isolated.spi.sck == config.spi.sck
    assert isolated.spi.mosi == config.spi.mosi
    assert isolated.spi.miso == config.spi.miso
    assert isolated.spi.enabled == config.spi.enabled
    assert isolated.buttons == config.buttons
    assert isolated.high_current_rail.pin == config.high_current_rail.pin
    assert isolated.high_current_rail.active_high == config.high_current_rail.active_high
    assert isolated.high_current_rail.enabled == config.high_current_rail.enabled


def test_isolate_never_disables_high_current_rail_declared_disabled(full_isolatable_config):
    """high_current_rail is excluded from isolation entirely -- even a section
    declared `enabled: false` stays exactly as declared, unlike an isolatable
    component's `enabled` field, which isolate never force-enables either."""
    full_isolatable_config["high_current_rail"] = {"pin": "GP28", "enabled": False}
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep="audio")

    assert isolated.high_current_rail.enabled is False


def _assert_same_fields_except_enabled(original, copy):
    for name in type(original).__slots__:
        if name == "enabled":
            continue
        assert getattr(copy, name) == getattr(original, name), (
            f"{type(original).__name__}.{name} was not preserved by the disabled copy"
        )


def test_isolate_disabled_copy_preserves_every_field_of_each_isolatable_section(
    full_isolatable_config,
):
    config = parse_device_config(full_isolatable_config)

    isolated_keeping_pixels = config.isolate(keep="pixels")
    _assert_same_fields_except_enabled(config.audio, isolated_keeping_pixels.audio)
    _assert_same_fields_except_enabled(config.ir, isolated_keeping_pixels.ir)
    _assert_same_fields_except_enabled(config.accelerometer, isolated_keeping_pixels.accelerometer)
    _assert_same_fields_except_enabled(config.magnetometer, isolated_keeping_pixels.magnetometer)
    _assert_same_fields_except_enabled(config.haptics, isolated_keeping_pixels.haptics)
    _assert_same_fields_except_enabled(config.radio, isolated_keeping_pixels.radio)
    _assert_same_fields_except_enabled(config.sdcard, isolated_keeping_pixels.sdcard)

    isolated_keeping_audio = config.isolate(keep="audio")
    for original_entry, isolated_entry in zip(config.pixels, isolated_keeping_audio.pixels):
        _assert_same_fields_except_enabled(original_entry, isolated_entry)


def test_isolate_disabled_copy_preserves_matrix_pixels_fields(matrix_config):
    config = parse_device_config(matrix_config)

    isolated = config.isolate(keep="audio")

    _assert_same_fields_except_enabled(config.pixels[0], isolated.pixels[0])
    assert isolated.pixels[0].enabled is False


def test_isolate_disabled_copy_preserves_neopixel_pixels_fields(neopixel_config):
    # A distinct entry type from `matrix_config`'s pixels[0] -- the generic
    # copy helper must serve NeoPixelPixelsConfig too, not just MatrixPixelsConfig.
    config = parse_device_config(neopixel_config)

    isolated = config.isolate(keep="audio")

    _assert_same_fields_except_enabled(config.pixels[0], isolated.pixels[0])
    assert isolated.pixels[0].enabled is False


def test_isolate_on_minimal_config_is_a_no_op_for_absent_components():
    config = parse_device_config({})

    isolated = config.isolate(keep="audio")

    assert isolated.audio is None
    assert isolated.ir is None
    assert isolated.accelerometer is None
    assert isolated.magnetometer is None
    assert isolated.haptics is None
    assert isolated.radio is None
    assert isolated.sdcard is None
    assert isolated.high_current_rail is None
    assert isolated.pixels == []


def test_isolate_unknown_keep_raises_value_error_naming_valid_choices_sorted():
    config = parse_device_config({})
    excluded = {"buttons", "i2c", "high_current_rail", "spi"}
    expected_choices = sorted(set(DeviceConfig.__slots__) - excluded)

    with pytest.raises(ValueError, match=", ".join(expected_choices)):
        config.isolate(keep="bogus")
