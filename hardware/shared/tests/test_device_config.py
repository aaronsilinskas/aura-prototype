"""Behaviour-driven tests for hardware/shared/device_config.py."""

import json
import re
from pathlib import Path

import pytest

from hardware.shared.device_config import (
    DeviceConfig,
    MatrixPixelsConfig,
    PinRef,
    load_device_config,
    parse_device_config,
    read_device_config_mapping,
    validate_band_map,
)
from hardware.shared.tests.pixels_config import as_matrix, as_neopixel

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_CONFIG_PATH = _REPO_ROOT / "examples" / "aura-device.pico-2.json"

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
    matrix_config["i2c"] = {"default": {"sda": "GP4", "scl": "GP5"}}
    matrix_config["spi"] = {"default": {"sck": "GP6", "mosi": "GP7", "miso": "GP8"}}
    matrix_config["radio"] = {"cs": "GP13", "reset": "GP14", "frequency": 915.0, "node": 5}
    matrix_config["sdcard"] = {"cs": "GP15"}
    matrix_config["accelerometer"] = {"address": "0x19"}
    matrix_config["magnetometer"] = {"address": "0x32"}
    matrix_config["haptics"] = {"address": "0x5B"}
    matrix_config["high_current_rail"] = {"pin": "GP28"}
    return matrix_config


# ---------------------------------------------------------------------------
# Happy path: full matrix config
# ---------------------------------------------------------------------------


def test_parse_full_matrix_config_maps_every_section(matrix_config):
    result = parse_device_config(matrix_config)

    assert len(result.pixels) == 1
    assert as_matrix(result.pixels[0]).cols == 13
    assert result.buttons == ["D9", "D10"]
    assert result.ir is not None
    assert result.ir.rx == ["D11"]
    assert result.ir.emitters["line"] == "D12"
    assert result.audio is not None
    assert result.audio.voices == 1
    assert result.audio.max_volume == 0.1
    assert result.audio.i2s_bit_clock == PinRef("I2S_BIT_CLOCK", "audio.i2s_bit_clock")
    assert result.audio.i2s_word_select == PinRef("I2S_WORD_SELECT", "audio.i2s_word_select")
    assert result.audio.i2s_data == PinRef("I2S_DATA", "audio.i2s_data")


def test_parse_matrix_config_scope_rows_converted_to_ranges(matrix_config):
    result = parse_device_config(matrix_config)

    scope_rows = as_matrix(result.pixels[0]).scope_rows
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

    assert as_matrix(result.pixels[0]).brightness == 1.0


def test_parse_matrix_explicit_brightness_is_stored(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 0.2

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).brightness == 0.2


def test_parse_matrix_brightness_boundary_zero_is_accepted(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 0.0

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).brightness == 0.0


def test_parse_matrix_brightness_boundary_one_is_accepted(matrix_config):
    matrix_config["pixels"][0]["brightness"] = 1.0

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).brightness == 1.0


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
# Matrix I2C address (_parse_address validator)
# ---------------------------------------------------------------------------


def test_parse_matrix_without_address_defaults_to_none(matrix_config):
    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address is None


def test_parse_matrix_integer_address_is_stored_as_int(matrix_config):
    matrix_config["pixels"][0]["address"] = 49

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address == 49


def test_parse_matrix_lowercase_hex_string_address_is_normalized_to_int(matrix_config):
    matrix_config["pixels"][0]["address"] = "0x31"

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address == 0x31


def test_parse_matrix_uppercase_hex_string_address_is_normalized_to_int(matrix_config):
    matrix_config["pixels"][0]["address"] = "0X31"

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address == 0x31


def test_parse_matrix_address_boundary_minimum_is_accepted(matrix_config):
    matrix_config["pixels"][0]["address"] = 0x08

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address == 0x08


def test_parse_matrix_address_boundary_maximum_is_accepted(matrix_config):
    matrix_config["pixels"][0]["address"] = 0x77

    result = parse_device_config(matrix_config)

    assert as_matrix(result.pixels[0]).address == 0x77


def test_parse_matrix_address_below_reserved_floor_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = 0x07

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
        parse_device_config(matrix_config)


def test_parse_matrix_address_above_reserved_ceiling_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = 0x78

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
        parse_device_config(matrix_config)


def test_parse_matrix_out_of_range_address_error_echoes_value_in_hex(matrix_config):
    matrix_config["pixels"][0]["address"] = 0x78

    with pytest.raises(ValueError, match="0x78"):
        parse_device_config(matrix_config)


def test_parse_matrix_boolean_address_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = True

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
        parse_device_config(matrix_config)


def test_parse_matrix_bare_decimal_string_address_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = "49"

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
        parse_device_config(matrix_config)


def test_parse_matrix_non_hex_string_address_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = "matrix"

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
        parse_device_config(matrix_config)


def test_parse_matrix_float_address_raises_value_error(matrix_config):
    matrix_config["pixels"][0]["address"] = 49.5

    with pytest.raises(ValueError, match=r"pixels\[0\]\.address"):
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


def test_parse_neopixel_first_entry_exposes_configured_scopes(neopixel_config):
    result = parse_device_config(neopixel_config)

    assert "personal" in as_neopixel(result.pixels[0]).scopes


def test_parse_neopixel_scope_fields_match(neopixel_config):
    result = parse_device_config(neopixel_config)

    scope = as_neopixel(result.pixels[0]).scopes["personal"]
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


@pytest.mark.parametrize("count", ["10", 10.0, True, 0, -1])
def test_parse_neopixel_scope_count_not_positive_integer_raises_value_error_naming_field(
    neopixel_config, count
):
    neopixel_config["pixels"][0]["scopes"]["personal"]["count"] = count

    with pytest.raises(
        ValueError, match=r"pixels\.scopes\.personal\.count must be a positive integer"
    ):
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


def test_parse_ir_without_rx_declares_no_receivers(matrix_config):
    del matrix_config["ir"]["rx"]

    result = parse_device_config(matrix_config)

    assert result.ir is not None
    assert result.ir.rx == []


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

    assert result.ir is not None
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

    assert result.ir is not None
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
# I2C-device validation (accelerometer, magnetometer, haptics) -- the three
# sections share one I2CDeviceConfig type and one _parse_i2c_device parser, so
# each rule below is asserted once, parametrized over every section, rather
# than spelled out three times.
# ---------------------------------------------------------------------------

_I2C_DEVICE_SECTIONS = ("accelerometer", "magnetometer", "haptics")


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_absent_i2c_device_section_yields_none(matrix_config, section):
    result = parse_device_config(matrix_config)

    assert getattr(result, section) is None


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_section_present_yields_non_none(matrix_config, section):
    matrix_config[section] = {}

    result = parse_device_config(matrix_config)

    assert getattr(result, section) is not None


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_unknown_key_raises_value_error_naming_field(matrix_config, section):
    matrix_config[section] = {"sensitivity": "high"}

    with pytest.raises(ValueError, match=rf"{section}\.sensitivity"):
        parse_device_config(matrix_config)


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_absent_enabled_key_defaults_to_true(matrix_config, section):
    matrix_config[section] = {}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).enabled is True


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_enabled_false_retains_object_not_none(matrix_config, section):
    matrix_config[section] = {"enabled": False}

    result = parse_device_config(matrix_config)

    parsed = getattr(result, section)
    assert parsed is not None
    assert parsed.enabled is False


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_non_boolean_enabled_raises_value_error_naming_field(
    matrix_config, section
):
    matrix_config[section] = {"enabled": "yes"}

    with pytest.raises(ValueError, match=rf"{section}\.enabled"):
        parse_device_config(matrix_config)


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_without_address_defaults_to_none(matrix_config, section):
    matrix_config[section] = {}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).address is None


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_integer_address_is_stored_as_int(matrix_config, section):
    matrix_config[section] = {"address": 0x19}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).address == 0x19


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_hex_string_address_is_normalized_to_int(matrix_config, section):
    matrix_config[section] = {"address": "0x19"}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).address == 0x19


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_out_of_range_address_raises_value_error_naming_field(
    matrix_config, section
):
    matrix_config[section] = {"address": 0x78}

    with pytest.raises(ValueError, match=rf"{section}\.address"):
        parse_device_config(matrix_config)


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_boolean_address_raises_value_error_naming_field(matrix_config, section):
    matrix_config[section] = {"address": True}

    with pytest.raises(ValueError, match=rf"{section}\.address"):
        parse_device_config(matrix_config)


@pytest.mark.parametrize("section", _I2C_DEVICE_SECTIONS)
def test_parse_i2c_device_bad_string_address_raises_value_error_naming_field(
    matrix_config, section
):
    matrix_config[section] = {"address": "25"}

    with pytest.raises(ValueError, match=rf"{section}\.address"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# I2C validation
# ---------------------------------------------------------------------------


def test_parse_i2c_section_maps_each_named_bus_to_its_pins(matrix_config):
    matrix_config["i2c"] = {
        "default": {"sda": "GP4", "scl": "GP5"},
        "sensors": {"sda": "GP6", "scl": "GP7"},
    }

    result = parse_device_config(matrix_config)

    assert {name: (bus.sda, bus.scl) for name, bus in result.i2c.items()} == {
        "default": (PinRef("GP4", "i2c.default.sda"), PinRef("GP5", "i2c.default.scl")),
        "sensors": (PinRef("GP6", "i2c.sensors.sda"), PinRef("GP7", "i2c.sensors.scl")),
    }


def test_parse_absent_i2c_section_declares_no_buses(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.i2c == {}


def test_parse_i2c_bus_missing_pins_names_each_with_its_bus_in_one_error(matrix_config):
    matrix_config["i2c"] = {"sensors": {}}

    with pytest.raises(
        ValueError,
        match=r"^i2c\.sensors\.sda, i2c\.sensors\.scl required together when i2c\.sensors",
    ):
        parse_device_config(matrix_config)


@pytest.mark.parametrize("pin", ["sda", "scl"])
def test_parse_i2c_bus_non_string_pin_raises_value_error_naming_the_bus(matrix_config, pin):
    matrix_config["i2c"] = {"sensors": {"sda": "GP6", "scl": "GP7", pin: 6}}

    with pytest.raises(ValueError, match=rf"i2c\.sensors\.{pin} must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_i2c_bus_has_no_enabled_key(matrix_config):
    matrix_config["i2c"] = {"default": {"sda": "GP4", "scl": "GP5", "enabled": True}}

    with pytest.raises(ValueError, match=r"i2c\.default\.enabled is not a valid key"):
        parse_device_config(matrix_config)


_MATRIX_ENTRY = {"type": "matrix", "cols": 13, "scope_rows": {"global.main": [0, 5]}}

# (field, raw config with one I2C device naming no bus, the device's parsed config)
_I2C_DEVICES = [
    ("accelerometer", {"accelerometer": {}}, lambda c: c.accelerometer),
    ("magnetometer", {"magnetometer": {}}, lambda c: c.magnetometer),
    ("haptics", {"haptics": {}}, lambda c: c.haptics),
    ("pixels[0]", {"pixels": [_MATRIX_ENTRY]}, lambda c: c.pixels[0]),
]
_I2C_DEVICE_IDS = [field for field, _raw, _device in _I2C_DEVICES]


def _naming_i2c_bus(raw: dict, bus: str) -> dict:
    """Return *raw* with its one I2C device naming *bus*."""
    ((section, value),) = raw.items()
    if section == "pixels":
        return {"pixels": [{**value[0], "i2c": bus}]}
    return {section: {**value, "i2c": bus}}


@pytest.mark.parametrize(("field", "raw", "device"), _I2C_DEVICES, ids=_I2C_DEVICE_IDS)
def test_an_i2c_device_naming_no_bus_joins_default(field, raw, device):
    assert device(parse_device_config(raw)).i2c == "default"


@pytest.mark.parametrize(("field", "raw", "device"), _I2C_DEVICES, ids=_I2C_DEVICE_IDS)
def test_an_i2c_device_may_name_default_explicitly_without_declaring_it(field, raw, device):
    assert device(parse_device_config(_naming_i2c_bus(raw, "default"))).i2c == "default"


@pytest.mark.parametrize(("field", "raw", "device"), _I2C_DEVICES, ids=_I2C_DEVICE_IDS)
def test_an_i2c_device_joins_the_declared_bus_it_names(field, raw, device):
    config = {"i2c": {"sensors": {"sda": "GP6", "scl": "GP7"}}, **_naming_i2c_bus(raw, "sensors")}

    assert device(parse_device_config(config)).i2c == "sensors"


@pytest.mark.parametrize(("field", "raw", "device"), _I2C_DEVICES, ids=_I2C_DEVICE_IDS)
def test_an_i2c_device_naming_an_undeclared_bus_raises_naming_the_field_and_bus(field, raw, device):
    config = {"i2c": {"default": {"sda": "GP4", "scl": "GP5"}}, **_naming_i2c_bus(raw, "snesors")}

    with pytest.raises(ValueError, match=rf"^{re.escape(field)}\.i2c names I2C bus 'snesors'"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# SPI validation
# ---------------------------------------------------------------------------


def test_parse_spi_section_maps_each_named_bus_to_its_pins(matrix_config):
    matrix_config["spi"] = {
        "default": {"sck": "GP2", "mosi": "GP3", "miso": "GP0"},
        "radio": {"sck": "GP14", "mosi": "GP15", "miso": "GP12"},
    }

    result = parse_device_config(matrix_config)

    assert {name: (bus.sck, bus.mosi, bus.miso) for name, bus in result.spi.items()} == {
        "default": (
            PinRef("GP2", "spi.default.sck"),
            PinRef("GP3", "spi.default.mosi"),
            PinRef("GP0", "spi.default.miso"),
        ),
        "radio": (
            PinRef("GP14", "spi.radio.sck"),
            PinRef("GP15", "spi.radio.mosi"),
            PinRef("GP12", "spi.radio.miso"),
        ),
    }


def test_parse_spi_bus_missing_pins_names_each_with_its_bus_in_one_error(matrix_config):
    matrix_config["spi"] = {"radio": {"mosi": "GP15"}}

    with pytest.raises(
        ValueError, match=r"^spi\.radio\.sck, spi\.radio\.miso required together when spi\.radio"
    ):
        parse_device_config(matrix_config)


def test_parse_spi_bus_non_string_pin_raises_value_error_naming_the_bus(matrix_config):
    matrix_config["spi"] = {"radio": {"sck": 14, "mosi": "GP15", "miso": "GP12"}}

    with pytest.raises(ValueError, match=r"spi\.radio\.sck must be a string pin name"):
        parse_device_config(matrix_config)


def test_parse_spi_bus_has_no_enabled_key(matrix_config):
    matrix_config["spi"] = {"default": {"sck": "A", "mosi": "B", "miso": "C", "enabled": True}}

    with pytest.raises(ValueError, match=r"spi\.default\.enabled is not a valid key"):
        parse_device_config(matrix_config)


def test_parse_absent_spi_section_declares_no_buses(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.spi == {}


_SPI_DEVICES = [
    ("radio", {"cs": "GP13", "reset": "GP11", "frequency": 915.0, "node": 1}),
    ("sdcard", {"cs": "GP1"}),
]
_SPI_DEVICE_IDS = [section for section, _raw in _SPI_DEVICES]


@pytest.mark.parametrize(("section", "raw"), _SPI_DEVICES, ids=_SPI_DEVICE_IDS)
def test_an_spi_device_naming_no_bus_joins_default(matrix_config, section, raw):
    matrix_config[section] = raw

    result = parse_device_config(matrix_config)

    assert getattr(result, section).spi == "default"


@pytest.mark.parametrize(("section", "raw"), _SPI_DEVICES, ids=_SPI_DEVICE_IDS)
def test_an_spi_device_may_name_default_explicitly_without_declaring_it(
    matrix_config, section, raw
):
    matrix_config[section] = {**raw, "spi": "default"}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).spi == "default"


@pytest.mark.parametrize(("section", "raw"), _SPI_DEVICES, ids=_SPI_DEVICE_IDS)
def test_an_spi_device_joins_the_declared_bus_it_names(matrix_config, section, raw):
    matrix_config["spi"] = {"radio": {"sck": "GP14", "mosi": "GP15", "miso": "GP12"}}
    matrix_config[section] = {**raw, "spi": "radio"}

    result = parse_device_config(matrix_config)

    assert getattr(result, section).spi == "radio"


@pytest.mark.parametrize(("section", "raw"), _SPI_DEVICES, ids=_SPI_DEVICE_IDS)
def test_an_spi_device_naming_an_undeclared_bus_raises_naming_the_field_and_bus(
    matrix_config, section, raw
):
    matrix_config["spi"] = {"default": {"sck": "GP2", "mosi": "GP3", "miso": "GP0"}}
    matrix_config[section] = {**raw, "spi": "radoi"}

    with pytest.raises(ValueError, match=rf"^{section}\.spi names SPI bus 'radoi'"):
        parse_device_config(matrix_config)


def test_an_undeclared_bus_error_lists_the_declared_buses_and_default_sorted(matrix_config):
    pins = {"sck": "GP14", "mosi": "GP15", "miso": "GP12"}
    matrix_config["spi"] = {"storage": pins, "radio": pins}
    matrix_config["radio"] = {"cs": "GP13", "reset": "GP11", "frequency": 915.0, "node": 1}
    matrix_config["radio"]["spi"] = "radoi"

    with pytest.raises(ValueError, match=r"valid buses: default, radio, storage$"):
        parse_device_config(matrix_config)


# ---------------------------------------------------------------------------
# Radio validation
# ---------------------------------------------------------------------------


def test_parse_radio_section_maps_cs_reset_frequency_node(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 42}

    result = parse_device_config(matrix_config)

    assert result.radio is not None
    assert result.radio.cs == PinRef("GP9", "radio.cs")
    assert result.radio.reset == PinRef("GP10", "radio.reset")
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

    assert result.radio is not None
    assert result.radio.node == 0


def test_parse_radio_node_boundary_254_is_accepted(matrix_config):
    matrix_config["radio"] = {"cs": "GP9", "reset": "GP10", "frequency": 915.0, "node": 254}

    result = parse_device_config(matrix_config)

    assert result.radio is not None
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

    assert result.radio is not None
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
    assert result.sdcard.cs == PinRef("GP9", "sdcard.cs")
    assert result.sdcard.mount == "/data"
    assert result.sdcard.enabled is False


def test_parse_sdcard_without_mount_defaults_to_slash_sd(matrix_config):
    matrix_config["sdcard"] = {"cs": "GP9"}

    result = parse_device_config(matrix_config)

    assert result.sdcard is not None
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

    assert result.sdcard is not None
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

    assert result.high_current_rail is not None
    assert result.high_current_rail.active_high is True


def test_parse_high_current_rail_non_boolean_active_high_raises_value_error(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28", "active_high": "yes"}

    with pytest.raises(ValueError, match=r"high_current_rail\.active_high"):
        parse_device_config(matrix_config)


def test_parse_high_current_rail_absent_enabled_key_defaults_to_true(matrix_config):
    matrix_config["high_current_rail"] = {"pin": "GP28"}

    result = parse_device_config(matrix_config)

    assert result.high_current_rail is not None
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
    """AudioConfig no longer carries a clips map (#804) -- clip names resolve
    through the Active scene namespace -- so a clips-free audio section parses with
    voices/max_volume/I2S validation unaffected."""
    result = parse_device_config(matrix_config)

    assert result.audio is not None
    assert result.audio.voices == 1
    assert result.audio.max_volume == 0.1
    assert result.audio.i2s_bit_clock.name == "I2S_BIT_CLOCK"
    assert not hasattr(result.audio, "clips")


def test_parse_absent_audio_section_yields_none(matrix_config):
    config = {"pixels": matrix_config["pixels"], "buttons": ["D9"]}

    result = parse_device_config(config)

    assert result.audio is None


def test_parse_audio_absent_enabled_key_defaults_to_true(matrix_config):
    result = parse_device_config(matrix_config)

    assert result.audio is not None
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
# Committed sample config — examples/aura-device.pico-2.json parses as-is
# ---------------------------------------------------------------------------


def test_committed_sample_device_config_parses():
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    result = parse_device_config(mapping)

    assert result.audio is not None
    assert result.audio.i2s_bit_clock.name == "GP21"
    assert result.audio.i2s_word_select.name == "GP22"
    assert result.audio.i2s_data.name == "GP20"
    assert result.accelerometer is not None
    assert result.haptics is not None
    assert result.radio is not None


def test_committed_sample_device_config_tunes_its_neopixel_strip_to_the_1000_ma_budget():
    # 24 px @ 1.0 x 60 mA = 1440 mA against a 1000 mA budget: 1000 / 1440.
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    result = parse_device_config(mapping)

    neopixel = next(p for p in result.pixels if not isinstance(p, MatrixPixelsConfig))
    assert neopixel.strips[0].brightness == pytest.approx(0.694, abs=0.001)


def test_committed_sample_device_config_matrix_and_magnetometer_no_longer_collide_at_0x30():
    """The Pico 2 board wires both the matrix and the MMC5603 magnetometer on
    the same I2C bus. The magnetometer has no configurable address and lives
    at its driver default (0x30), so the matrix must declare a distinct
    override (#834) rather than also defaulting to 0x30."""
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    result = parse_device_config(mapping)

    matrix_entries = [p for p in result.pixels if isinstance(p, MatrixPixelsConfig)]
    assert len(matrix_entries) == 1
    assert matrix_entries[0].address == 0x31
    assert result.magnetometer is not None
    assert result.magnetometer.enabled is True


def test_committed_sample_device_config_carries_no_clips_map():
    """hardware_test's sfx_test clip resolves to its scene-local
    hardware_test/sounds/sfx_test_start.wav (#804), not a device-config
    clips map."""
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    assert "clips" not in mapping["audio"]


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

    assert config.ir is not None
    assert config.accelerometer is not None
    assert config.magnetometer is not None
    assert config.haptics is not None
    assert config.radio is not None
    assert config.sdcard is not None
    assert config.high_current_rail is not None
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

    assert isolated.audio is not None
    assert isolated.audio.enabled is False


@pytest.mark.parametrize("keep", _ISOLATABLE_COMPONENTS)
def test_isolate_never_touches_i2c_spi_buttons_or_high_current_rail(full_isolatable_config, keep):
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep=keep)

    assert isolated.i2c == config.i2c
    assert isolated.spi == config.spi
    assert isolated.buttons == config.buttons
    assert isolated.high_current_rail is not None
    assert config.high_current_rail is not None
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

    assert isolated.high_current_rail is not None
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
    matrix_config["pixels"][0]["address"] = "0x31"
    config = parse_device_config(matrix_config)

    isolated = config.isolate(keep="audio")

    _assert_same_fields_except_enabled(config.pixels[0], isolated.pixels[0])
    assert as_matrix(isolated.pixels[0]).address == 0x31
    assert isolated.pixels[0].enabled is False


def test_isolate_disabled_copy_preserves_accelerometer_magnetometer_and_haptics_address(
    full_isolatable_config,
):
    config = parse_device_config(full_isolatable_config)

    isolated = config.isolate(keep="pixels")

    assert isolated.accelerometer is not None
    assert config.accelerometer is not None
    assert isolated.magnetometer is not None
    assert config.magnetometer is not None
    assert isolated.haptics is not None
    assert config.haptics is not None
    assert isolated.accelerometer.address == config.accelerometer.address == 0x19
    assert isolated.magnetometer.address == config.magnetometer.address == 0x32
    assert isolated.haptics.address == config.haptics.address == 0x5B


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
    expected_choices = "accelerometer, audio, haptics, ir, magnetometer, pixels, radio, sdcard"

    with pytest.raises(ValueError, match=expected_choices):
        config.isolate(keep="bogus")
