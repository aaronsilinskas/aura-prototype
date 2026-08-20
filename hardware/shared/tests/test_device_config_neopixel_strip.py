"""Behaviour-driven tests for NeoPixelStripConfig parsing in device_config.py.

Covers the new scope_pixels segmented-strip shape introduced in issue #482.
"""

import pytest

from hardware.shared.device_config import (
    NeoPixelPixelsConfig,
    parse_device_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_strip_config():
    """A neopixel entry with two scope_pixels segments on one strip."""
    return {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 30,
                "scope_pixels": {
                    "personal": [0, 10],
                    "ambient": [10, 30],
                },
            }
        ],
        "buttons": ["D9"],
    }


@pytest.fixture
def two_strip_config():
    """Two separate neopixel entries, each with their own scope_pixels."""
    return {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 20,
                "scope_pixels": {
                    "personal": [0, 10],
                    "directional": [10, 20],
                },
            },
            {
                "type": "neopixel",
                "pin": "D6",
                "count": 10,
                "scope_pixels": {
                    "ambient": [0, 10],
                },
            },
        ],
        "buttons": ["D9"],
    }


# ---------------------------------------------------------------------------
# Happy path: single segmented strip
# ---------------------------------------------------------------------------


def test_parse_neopixel_entry_produces_single_pixels_output(single_strip_config):
    result = parse_device_config(single_strip_config)

    assert len(result.pixels) == 1


def test_parse_neopixel_entry_produces_single_strip(single_strip_config):
    result = parse_device_config(single_strip_config)

    assert len(result.pixels[0].strips) == 1


def test_parse_neopixel_strip_pin_matches(single_strip_config):
    result = parse_device_config(single_strip_config)

    strip = result.pixels[0].strips[0]
    assert strip.pin == "D5"


def test_parse_neopixel_strip_count_matches(single_strip_config):
    result = parse_device_config(single_strip_config)

    strip = result.pixels[0].strips[0]
    assert strip.count == 30


def test_parse_neopixel_strip_order_defaults_to_grb(single_strip_config):
    result = parse_device_config(single_strip_config)

    strip = result.pixels[0].strips[0]
    assert strip.order == "GRB"


def test_parse_neopixel_strip_brightness_defaults_to_one(single_strip_config):
    result = parse_device_config(single_strip_config)

    strip = result.pixels[0].strips[0]
    assert strip.brightness == 1.0


def test_parse_neopixel_strip_scope_pixels_converted_to_ranges(single_strip_config):
    result = parse_device_config(single_strip_config)

    scope_pixels = result.pixels[0].strips[0].scope_pixels
    assert scope_pixels["personal"] == range(0, 10)
    assert scope_pixels["ambient"] == range(10, 30)


def test_parse_neopixel_strip_explicit_order_and_brightness():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "order": "RGB",
                "brightness": 0.5,
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    result = parse_device_config(config)

    strip = result.pixels[0].strips[0]
    assert strip.order == "RGB"
    assert strip.brightness == 0.5


# ---------------------------------------------------------------------------
# Validation: strip brightness
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_non_numeric_brightness_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "brightness": "bright",
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(config)


def test_parse_neopixel_strip_out_of_range_brightness_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "brightness": 1.5,
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(config)


def test_parse_neopixel_strip_negative_brightness_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "brightness": -0.5,
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"pixels\[0\]\.brightness"):
        parse_device_config(config)


def test_parse_neopixel_strip_brightness_boundary_zero_is_accepted():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "brightness": 0.0,
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    result = parse_device_config(config)

    assert result.pixels[0].strips[0].brightness == 0.0


# ---------------------------------------------------------------------------
# Happy path: two separate strip entries
# ---------------------------------------------------------------------------


def test_parse_two_neopixel_strips_yields_two_entries(two_strip_config):
    result = parse_device_config(two_strip_config)

    total_strips = sum(len(p.strips) for p in result.pixels if isinstance(p, NeoPixelPixelsConfig))
    assert total_strips == 2


def test_parse_two_neopixel_strips_correct_pins(two_strip_config):
    result = parse_device_config(two_strip_config)

    strips = [s for p in result.pixels if isinstance(p, NeoPixelPixelsConfig) for s in p.strips]
    pins = {s.pin for s in strips}
    assert pins == {"D5", "D6"}


# ---------------------------------------------------------------------------
# Validation: scope_pixels required and non-empty
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_missing_scope_pixels_raises_value_error():
    config = {
        "pixels": [{"type": "neopixel", "pin": "D5", "count": 10}],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope_pixels"):
        parse_device_config(config)


def test_parse_neopixel_strip_empty_scope_pixels_raises_value_error():
    config = {
        "pixels": [{"type": "neopixel", "pin": "D5", "count": 10, "scope_pixels": {}}],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope_pixels"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: pin required
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_missing_pin_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"pin"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: count required
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_missing_count_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "scope_pixels": {"personal": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"count"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: unknown scope key
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_unknown_scope_key_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"bad_scope": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="bad_scope"):
        parse_device_config(config)


def test_parse_neopixel_strip_unknown_scope_key_error_lists_valid_keys():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"bad_scope": [0, 10]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="personal"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: out-of-range segment
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_segment_start_below_zero_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [-1, 5]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope 'personal'.*is out of range"):
        parse_device_config(config)


def test_parse_neopixel_strip_segment_end_exceeds_count_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 11]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope 'personal'.*is out of range"):
        parse_device_config(config)


def test_parse_neopixel_strip_inverted_segment_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [5, 2]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope 'personal'.*is out of range"):
        parse_device_config(config)


def test_parse_neopixel_strip_out_of_range_error_names_pin():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 20]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="D5"):
        parse_device_config(config)


def test_parse_neopixel_strip_out_of_range_error_names_scope():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 20]},
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match=r"scope 'personal'.*requires 0 <= start < end <= count"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: overlapping segments on one strip
# ---------------------------------------------------------------------------


def test_parse_neopixel_strip_overlapping_segments_raise_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 30,
                "scope_pixels": {
                    "personal": [0, 15],
                    "ambient": [10, 30],
                },
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="overlap"):
        parse_device_config(config)


def test_parse_neopixel_strip_overlapping_segments_error_names_conflicting_scopes():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 30,
                "scope_pixels": {
                    "personal": [0, 15],
                    "ambient": [10, 30],
                },
            }
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="personal"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Validation: duplicate pin across strip entries
# ---------------------------------------------------------------------------


def test_parse_neopixel_duplicate_pin_raises_value_error():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
            {
                "type": "neopixel",
                "pin": "D5",  # same pin as above
                "count": 10,
                "scope_pixels": {"ambient": [0, 10]},
            },
        ],
        "buttons": ["D9"],
    }

    with pytest.raises(ValueError, match="D5"):
        parse_device_config(config)


# ---------------------------------------------------------------------------
# Same scope key on multiple strips (mirrored outputs — issue #483)
# ---------------------------------------------------------------------------


def test_parse_two_strips_sharing_scope_key_produces_two_strip_configs():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
            {
                "type": "neopixel",
                "pin": "D6",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
        ],
        "buttons": ["D9"],
    }

    result = parse_device_config(config)

    strips = [s for p in result.pixels if isinstance(p, NeoPixelPixelsConfig) for s in p.strips]
    assert len(strips) == 2


def test_parse_two_strips_sharing_scope_key_preserves_both_pins():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
            {
                "type": "neopixel",
                "pin": "D6",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
        ],
        "buttons": ["D9"],
    }

    result = parse_device_config(config)

    strips = [s for p in result.pixels if isinstance(p, NeoPixelPixelsConfig) for s in p.strips]
    pins = {s.pin for s in strips}
    assert pins == {"D5", "D6"}


def test_parse_two_strips_sharing_scope_key_each_strip_has_scope_pixels():
    config = {
        "pixels": [
            {
                "type": "neopixel",
                "pin": "D5",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
            {
                "type": "neopixel",
                "pin": "D6",
                "count": 10,
                "scope_pixels": {"personal": [0, 10]},
            },
        ],
        "buttons": ["D9"],
    }

    result = parse_device_config(config)

    strips = [s for p in result.pixels if isinstance(p, NeoPixelPixelsConfig) for s in p.strips]
    for strip in strips:
        assert "personal" in strip.scope_pixels
