"""Behaviour-driven tests for hardware/shared/device_config.py."""

import json
from pathlib import Path

import pytest

from hardware.shared.device_config import (
    DeviceConfig,
    first_neopixel_pin,
    load_device_config,
    parse_device_config,
    read_device_config_mapping,
    require_pin,
    validate_band_map,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_CONFIG_PATH = _REPO_ROOT / "examples" / "aura-device.sample.json"

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
            "clips": {
                "sfx_test_start": "sounds/blip.wav",
            },
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


# ---------------------------------------------------------------------------
# Happy path: full matrix config
# ---------------------------------------------------------------------------


def test_parse_full_matrix_config_maps_every_section(matrix_config):
    result = parse_device_config(matrix_config)

    assert len(result.pixels) == 1
    assert result.pixels[0].cols == 13
    assert result.buttons == ["D9", "D10"]
    assert result.ir is not None
    assert result.ir.rx == "D11"
    assert result.ir.emitters["line"] == "D12"
    assert result.audio is not None
    assert result.audio.voices == 1
    assert result.audio.max_volume == 0.1
    assert result.audio.clips == {"sfx_test_start": "sounds/blip.wav"}
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
# Button validation
# ---------------------------------------------------------------------------


def test_parse_no_buttons_raises_value_error(matrix_config):
    matrix_config["buttons"] = []

    with pytest.raises(ValueError, match="buttons"):
        parse_device_config(matrix_config)


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


def test_parse_ir_without_line_raises_value_error(matrix_config):
    del matrix_config["ir"]["line"]

    with pytest.raises(ValueError, match=r"ir\.line"):
        parse_device_config(matrix_config)


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


def test_parse_absent_audio_section_yields_none(matrix_config):
    config = {"pixels": matrix_config["pixels"], "buttons": ["D9"]}

    result = parse_device_config(config)

    assert result.audio is None


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
# Committed sample config — examples/aura-device.sample.json parses as-is
# ---------------------------------------------------------------------------


def test_committed_sample_device_config_parses():
    mapping = read_device_config_mapping(str(_SAMPLE_CONFIG_PATH))

    result = parse_device_config(mapping)

    assert result.audio is not None
    assert result.audio.i2s_bit_clock == "I2S_BIT_CLOCK"
    assert result.audio.i2s_word_select == "I2S_WORD_SELECT"
    assert result.audio.i2s_data == "I2S_DATA"


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
