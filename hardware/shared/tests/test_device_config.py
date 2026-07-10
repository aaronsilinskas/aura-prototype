"""Behaviour-driven tests for hardware/shared/device_config.py."""

import json

import pytest

from hardware.shared.device_config import (
    DeviceConfig,
    parse_device_config,
    read_device_config_mapping,
    validate_band_map,
)

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
# pixels list shape: empty and duplicate matrix
# ---------------------------------------------------------------------------


def test_parse_pixels_given_as_dict_raises_value_error(matrix_config):
    matrix_config["pixels"] = matrix_config["pixels"][0]  # old single-object shape

    with pytest.raises(ValueError, match="list"):
        parse_device_config(matrix_config)


def test_parse_empty_pixels_list_raises_value_error(matrix_config):
    matrix_config["pixels"] = []

    with pytest.raises(ValueError, match="at least one"):
        parse_device_config(matrix_config)


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
