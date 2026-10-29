"""The Device assembly turns a ``DeviceConfig`` into ``DeviceHardware`` through ``DeviceParts``."""

from __future__ import annotations

import re
from typing import Any, cast

import pytest

from engine.input import ButtonData
from engine.log import Logger
from engine.network import AREA_OF_EFFECT, CONE, LINE
from hardware.shared.device_assembly import assemble_device
from hardware.shared.device_config import DeviceConfig, parse_device_config
from hardware.shared.device_hardware import DeviceHardware
from hardware.shared.device_parts import PinRef
from hardware.shared.polled_sensor import PolledSensor
from hardware.shared.radio_transceiver import RadioTransceiver
from hardware.shared.tests.recording_parts import Output, PartError, RecordingParts

_NEOPIXEL = {"type": "neopixel", "pin": "GP0", "count": 4, "scope_pixels": {"personal": [0, 4]}}
_MATRIX = {"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}
_AUDIO = {
    "voices": 2,
    "i2s_bit_clock": "GP10",
    "i2s_word_select": "GP11",
    "i2s_data": "GP12",
}
_RADIO = {"cs": "GP13", "reset": "GP14", "frequency": 915.0, "node": 3}
_SDCARD = {"cs": "GP15", "mount": "/sd"}
_IR = {"rx": "GP5", "line": "GP6"}
_RAIL = {"pin": "GP20"}

# Every gated section, its config, and the part it asks for.
_SECTIONS = [
    ("accelerometer", {}, "accelerometer"),
    ("magnetometer", {}, "magnetometer"),
    ("haptics", {}, "haptic_output"),
    ("audio", _AUDIO, "audio_output"),
    ("radio", _RADIO, "radio_transport"),
    ("sdcard", _SDCARD, "storage"),
    ("ir", _IR, "ir_reader"),
]
_SECTION_IDS = [section for section, _config, _part in _SECTIONS]


def _config(**sections: object) -> DeviceConfig:
    return parse_device_config(sections)


def _assemble(config: DeviceConfig, **parts_options: Any) -> tuple[DeviceHardware, RecordingParts]:
    parts = RecordingParts(**parts_options)
    return assemble_device(config, parts), parts


def _narration(config: DeviceConfig, **parts_options: Any) -> str:
    fragments: list[str] = []
    assemble_device(config, RecordingParts(**parts_options), Logger("[hw]", fragments.append))
    return "".join(fragments)


def _disabled(section_config: dict) -> dict:
    return {**section_config, "enabled": False}


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("section", "section_config", "part"), _SECTIONS, ids=_SECTION_IDS)
def test_a_declared_enabled_section_asks_for_its_part(section, section_config, part):
    _hw, parts = _assemble(_config(**{section: section_config}))

    assert part in parts.parts()


@pytest.mark.parametrize(("section", "section_config", "part"), _SECTIONS, ids=_SECTION_IDS)
def test_an_absent_section_asks_for_no_part(section, section_config, part):
    _hw, parts = _assemble(_config())

    assert part not in parts.parts()


@pytest.mark.parametrize("section", _SECTION_IDS)
def test_an_absent_section_narrates_no_line(section):
    assert not re.search(rf"^\[hw\] {section}\b", _narration(_config()), re.MULTILINE)


@pytest.mark.parametrize(("section", "section_config", "part"), _SECTIONS, ids=_SECTION_IDS)
def test_a_disabled_section_asks_for_no_part_and_narrates_disabled(section, section_config, part):
    config = _config(**{section: _disabled(section_config)})

    _hw, parts = _assemble(config)

    assert part not in parts.parts()
    assert re.search(rf"^\[hw\] {section}\b.* disabled$", _narration(config), re.MULTILINE)


def test_a_config_disabling_every_gated_section_builds_no_optional_hardware():
    config = _config(**{section: _disabled(c) for section, c, _part in _SECTIONS})

    hw, _parts = _assemble(config)

    assert (
        hw.outputs,
        hw.accelerometer,
        hw.magnetometer,
        hw.ir,
        hw.radio,
        hw.storage,
    ) == ([], None, None, None, None, None)


@pytest.mark.parametrize(
    ("section", "field"), [("accelerometer", "accelerometer"), ("magnetometer", "magnetometer")]
)
def test_a_sensor_section_is_built_with_its_config_on_the_i2c_bus(section, field):
    hw, parts = _assemble(_config(**{section: {"address": 0x19}}))

    ((sensor_config, bus),) = parts.args_of(section)
    assert (sensor_config.address, bus.kind) == (0x19, "i2c")
    assert getattr(hw, field) is not None


@pytest.mark.parametrize("sensor", ["accelerometer", "magnetometer"])
def test_an_enabled_sensor_reads_zero_before_its_first_update(sensor):
    hw, _parts = _assemble(_config(**{sensor: {}}))

    polled = getattr(hw, sensor)
    assert polled is not None
    reading = polled.reading
    assert (reading.x, reading.y, reading.z) == (0.0, 0.0, 0.0)


def test_an_enabled_accelerometer_section_is_a_polled_sensor_reading_its_part():
    hw, parts = _assemble(_config(accelerometer={}))
    parts.acceleration = (1.0, 2.0, 3.0)

    assert isinstance(hw.accelerometer, PolledSensor)
    hw.accelerometer.update()
    reading = hw.accelerometer.reading
    assert (reading.x, reading.y, reading.z) == (1.0, 2.0, 3.0)


def test_an_enabled_magnetometer_section_is_a_polled_sensor_reading_its_part():
    hw, parts = _assemble(_config(magnetometer={}))
    parts.magnetic = (4.0, 5.0, 6.0)

    assert isinstance(hw.magnetometer, PolledSensor)
    hw.magnetometer.update()
    reading = hw.magnetometer.reading
    assert (reading.x, reading.y, reading.z) == (4.0, 5.0, 6.0)


@pytest.mark.parametrize(
    ("sensor", "reading_attr"),
    [("accelerometer", "acceleration"), ("magnetometer", "magnetic")],
)
def test_a_sensor_logs_a_read_failing_line_under_its_section_name_to_the_assembly_logger(
    sensor, reading_attr
):
    fragments: list[str] = []
    parts = RecordingParts()
    hw = assemble_device(_config(**{sensor: {}}), parts, Logger("[hw]", fragments.append))
    setattr(parts, reading_attr, (1.0, 2.0))  # not 3-tuple: a failed read
    del fragments[:]

    getattr(hw, sensor).update()

    assert "".join(fragments).startswith(f"[hw] {sensor} read failing: ValueError(")


def test_haptics_are_built_with_their_config_on_the_i2c_bus():
    _hw, parts = _assemble(_config(haptics={"address": 0x5B}))

    ((haptics_config, bus),) = parts.args_of("haptic_output")
    assert (haptics_config.address, bus.kind) == (0x5B, "i2c")


def test_disabled_audio_builds_no_audio_output():
    hw, _parts = _assemble(_config(pixels=[_NEOPIXEL], audio=_disabled(_AUDIO)))

    assert [cast(Output, output).part for output in hw.outputs] == ["neopixel_strip"]


def test_a_disabled_sdcard_builds_no_storage():
    hw, _parts = _assemble(_config(sdcard=_disabled(_SDCARD)))

    assert hw.storage is None


def test_no_rail_section_drives_no_rail_pin():
    _hw, parts = _assemble(_config())

    assert "high_current_rail" not in parts.parts()


@pytest.mark.parametrize("bus", ["i2c", "spi"])
def test_a_disabled_bus_is_not_built(bus):
    pins = {"i2c": {"sda": "GP0", "scl": "GP1"}, "spi": {"sck": "A", "mosi": "B", "miso": "C"}}

    _hw, parts = _assemble(_config(**{bus: _disabled(pins[bus])}))

    assert f"{bus}_bus" not in parts.parts()


def test_with_no_bus_sections_both_buses_are_built_on_the_board_defaults():
    _hw, parts = _assemble(_config())

    assert parts.args_of("i2c_bus") == [(None, None)]
    assert parts.args_of("spi_bus") == [(None, None, None)]


def test_declared_bus_pins_reach_the_bus_parts_with_their_fields():
    _hw, parts = _assemble(
        _config(
            i2c={"sda": "GP4", "scl": "GP5"}, spi={"sck": "GP18", "mosi": "GP19", "miso": "GP16"}
        )
    )

    assert parts.args_of("i2c_bus") == [(PinRef("GP5", "i2c.scl"), PinRef("GP4", "i2c.sda"))]
    assert parts.args_of("spi_bus") == [
        (PinRef("GP18", "spi.sck"), PinRef("GP19", "spi.mosi"), PinRef("GP16", "spi.miso"))
    ]


@pytest.mark.parametrize("entry", [_NEOPIXEL, _MATRIX], ids=["neopixel", "matrix"])
def test_a_disabled_pixel_entry_asks_for_no_part(entry):
    _hw, parts = _assemble(
        _config(i2c={"sda": "A", "scl": "B", "enabled": False}, pixels=[_disabled(entry)])
    )

    assert not {"neopixel_strip", "matrix_pixels"} & set(parts.parts())


def test_an_enabled_matrix_entry_is_built_on_the_i2c_bus():
    _hw, parts = _assemble(_config(pixels=[_MATRIX]))

    ((matrix_config, bus),) = parts.args_of("matrix_pixels")
    assert (matrix_config.cols, bus.kind) == (13, "i2c")


def test_each_neopixel_strip_is_built_on_its_pin():
    _hw, parts = _assemble(
        _config(
            pixels=[_NEOPIXEL, {**_NEOPIXEL, "pin": "GP1", "scope_pixels": {"ambient": [0, 4]}}]
        )
    )

    assert [(strip.scope_pixels, pin) for strip, pin in parts.args_of("neopixel_strip")] == [
        ({"personal": range(0, 4)}, PinRef("GP0", "pixels.pin")),
        ({"ambient": range(0, 4)}, PinRef("GP1", "pixels.pin")),
    ]


@pytest.mark.parametrize(
    "entries",
    [[_MATRIX, _NEOPIXEL], [_NEOPIXEL, _MATRIX]],
    ids=["matrix-first", "neopixel-first"],
)
def test_pixel_outputs_follow_config_order(entries):
    hw, _parts = _assemble(_config(pixels=entries))

    expected = ["matrix_pixels" if e is _MATRIX else "neopixel_strip" for e in entries]
    assert [cast(Output, output).part for output in hw.outputs] == expected


def test_a_segmented_strip_is_one_strip_carrying_every_segment():
    entry = {**_NEOPIXEL, "count": 20, "scope_pixels": {"personal": [0, 10], "ambient": [10, 20]}}

    hw, parts = _assemble(_config(pixels=[entry]))

    ((strip, pin),) = parts.args_of("neopixel_strip")
    assert (strip.scope_pixels, pin) == (
        {"personal": range(0, 10), "ambient": range(10, 20)},
        PinRef("GP0", "pixels.pin"),
    )
    assert len(hw.outputs) == 1


def test_a_legacy_entry_with_several_scopes_is_one_strip_per_scope_with_its_own_settings():
    legacy = {
        "type": "neopixel",
        "scopes": {
            "personal": {"pin": "GP2", "count": 10, "brightness": 0.5},
            "directional": {"pin": "GP3", "count": 4, "order": "RGB"},
        },
    }

    hw, parts = _assemble(_config(pixels=[legacy]))

    assert [
        (strip.scope_pixels, strip.brightness, strip.order, pin)
        for strip, pin in parts.args_of("neopixel_strip")
    ] == [
        ({"personal": range(0, 10)}, 0.5, "GRB", PinRef("GP2", "pixels.scopes.personal.pin")),
        ({"directional": range(0, 4)}, 1.0, "RGB", PinRef("GP3", "pixels.scopes.directional.pin")),
    ]
    assert len(hw.outputs) == 2


def test_a_legacy_scope_entry_is_one_strip_per_scope_spanning_it():
    legacy = {"type": "neopixel", "scopes": {"personal": {"pin": "GP2", "count": 6}}}

    _hw, parts = _assemble(_config(pixels=[legacy]))

    ((strip, pin),) = parts.args_of("neopixel_strip")
    assert (strip.count, strip.scope_pixels, pin) == (
        6,
        {"personal": range(0, 6)},
        PinRef("GP2", "pixels.scopes.personal.pin"),
    )


# ---------------------------------------------------------------------------
# Bus requirements
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section", ["accelerometer", "magnetometer", "haptics"])
@pytest.mark.parametrize("no_bus", ["disabled", "unbuildable"])
def test_an_i2c_chip_section_without_an_i2c_bus_is_rejected(section, no_bus):
    if no_bus == "disabled":
        i2c, options = {"i2c": {"sda": "A", "scl": "B", "enabled": False}}, {}
    else:
        i2c, options = {}, {"no_i2c": True}
    config = _config(**i2c, **{section: {}})

    with pytest.raises(
        RuntimeError, match=f"^{section} section is declared but no I2C bus is available$"
    ):
        _assemble(config, **options)


def test_an_enabled_matrix_entry_without_an_i2c_bus_is_rejected():
    message = r"^pixels\.type is 'matrix' but no I2C bus is available$"
    with pytest.raises(RuntimeError, match=message):
        _assemble(_config(pixels=[_MATRIX]), no_i2c=True)


@pytest.mark.parametrize(("section", "section_config"), [("radio", _RADIO), ("sdcard", _SDCARD)])
def test_an_spi_section_with_its_bus_disabled_is_rejected(section, section_config):
    config = _config(
        spi={"sck": "A", "mosi": "B", "miso": "C", "enabled": False}, **{section: section_config}
    )

    with pytest.raises(
        RuntimeError, match=f"^{section} section is declared but no SPI bus is available$"
    ):
        _assemble(config)


def test_an_unbuildable_i2c_bus_is_narrated_as_no_bus():
    assert "[hw] i2c default no bus\n" in _narration(_config(), no_i2c=True)


# ---------------------------------------------------------------------------
# High-current rail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("active_high", "enabled", "level", "note"),
    [
        (True, True, True, "asserted"),
        (False, True, False, "asserted"),
        (True, False, False, "held off"),
        (False, False, True, "held off"),
    ],
    ids=["active-high-on", "active-low-on", "active-high-off", "active-low-off"],
)
def test_the_rail_is_driven_asserted_when_enabled_and_deasserted_when_disabled(
    active_high, enabled, level, note
):
    config = _config(high_current_rail={**_RAIL, "active_high": active_high, "enabled": enabled})

    _hw, parts = _assemble(config)

    assert parts.args_of("high_current_rail") == [(PinRef("GP20", "high_current_rail.pin"), level)]
    assert f"[hw] high_current_rail pin=GP20 active_high={active_high} {note}\n" in _narration(
        config
    )


# ---------------------------------------------------------------------------
# Build order
# ---------------------------------------------------------------------------


def test_parts_come_up_rail_buses_pixels_buttons_sensors_audio_haptics_radio_storage_ir():
    config = _config(
        ir=_IR,
        sdcard=_SDCARD,
        radio=_RADIO,
        haptics={},
        audio=_AUDIO,
        magnetometer={},
        accelerometer={},
        buttons=["GP3"],
        pixels=[_NEOPIXEL],
        high_current_rail=_RAIL,
    )

    _hw, parts = _assemble(config)

    assert parts.parts() == [
        "board_name",
        "high_current_rail",
        "i2c_bus",
        "spi_bus",
        "neopixel_strip",
        "button_reader",
        "accelerometer",
        "magnetometer",
        "audio_output",
        "haptic_output",
        "radio_transport",
        "storage",
        "ir_reader",
        "ir_writer",
    ]


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------


def test_a_boot_narrates_begin_each_step_and_ready():
    config = _config(buttons=["GP3", "GP4"], pixels=[_NEOPIXEL], ir=_IR, accelerometer={})

    text = _narration(config)

    lines = text.splitlines()
    assert lines[:-1] == [
        "[hw] begin board=test-board",
        "[hw] i2c default ok",
        "[hw] spi default ok",
        "[hw] pixels[0] neopixel pin=GP0 count=4 order=GRB "
        + "scope_pixels=[personal:0-4] brightness=1.00 ok",
        "[hw] buttons A=GP3 B=GP4 ok",
        "[hw] accelerometer lis3dh ok",
        "[hw] ir rx=[GP5] emitters=line:GP6 writer=fake ok",
    ]
    assert re.fullmatch(r"\[hw\] ready outputs=1 buttons=2 elapsed_s=\d+\.\d{3}", lines[-1])


_EVERY_SECTION = {
    "high_current_rail": {"pin": "GP28", "active_high": True},
    "i2c": {"sda": "GP4", "scl": "GP5"},
    "spi": {"sck": "SCK", "mosi": "MOSI", "miso": "MISO"},
    "pixels": [
        {"type": "matrix", "cols": 13, "scope_rows": {"global.main": [0, 5]}},
        {"type": "neopixel", "scopes": {"personal": {"pin": "D5", "count": 10}}},
    ],
    "buttons": ["D9"],
    "accelerometer": {},
    "magnetometer": {},
    "audio": {
        "voices": 1,
        "max_volume": 0.5,
        "i2s_bit_clock": "I2S_BIT_CLOCK",
        "i2s_word_select": "I2S_WORD_SELECT",
        "i2s_data": "I2S_DATA",
    },
    "haptics": {},
    "radio": {"cs": "D24", "reset": "D25", "frequency": 915.0, "node": 1},
    "sdcard": {"cs": "D26", "mount": "/sd"},
    "ir": {"rx": "D11", "line": "D12"},
}


def test_a_config_declaring_every_section_narrates_each_built_in_build_order():
    lines = _narration(parse_device_config(_EVERY_SECTION), writer_kind="pio").splitlines()

    assert lines[:-1] == [
        "[hw] begin board=test-board",
        "[hw] high_current_rail pin=GP28 active_high=True asserted",
        "[hw] i2c scl=GP5 sda=GP4 ok",
        "[hw] spi sck=SCK mosi=MOSI miso=MISO ok",
        "[hw] pixels[0] matrix cols=13 scope_rows=[global.main:0-5] brightness=1.00 ok",
        "[hw] pixels[1] neopixel pin=D5 count=10 order=GRB scope=personal brightness=1.00 ok",
        "[hw] buttons A=D9 ok",
        "[hw] accelerometer lis3dh ok",
        "[hw] magnetometer mmc5603 ok",
        "[hw] audio voices=1 max_volume=0.50 i2s_bit_clock=I2S_BIT_CLOCK "
        + "i2s_word_select=I2S_WORD_SELECT i2s_data=I2S_DATA ok",
        "[hw] haptics drv2605 ok",
        "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 ok",
        "[hw] sdcard mount=/sd cs=D26 ok",
        "[hw] ir rx=[D11] emitters=line:D12 writer=pio ok",
    ]
    assert re.fullmatch(r"\[hw\] ready outputs=4 buttons=1 elapsed_s=\d+\.\d{3}", lines[-1])


def test_a_config_disabling_every_section_narrates_each_disabled_in_build_order():
    every_disabled = {
        name: section if name == "buttons" else _disabled(section)
        for name, section in _EVERY_SECTION.items()
        if name != "pixels"
    }
    every_disabled["pixels"] = [_disabled(entry) for entry in _EVERY_SECTION["pixels"]]

    lines = _narration(parse_device_config(every_disabled)).splitlines()

    assert lines[:-1] == [
        "[hw] begin board=test-board",
        "[hw] high_current_rail pin=GP28 active_high=True held off",
        "[hw] i2c disabled",
        "[hw] spi disabled",
        "[hw] pixels[0] matrix disabled",
        "[hw] pixels[1] neopixel disabled",
        "[hw] buttons A=D9 ok",
        "[hw] accelerometer lis3dh disabled",
        "[hw] magnetometer mmc5603 disabled",
        "[hw] audio disabled",
        "[hw] haptics drv2605 disabled",
        "[hw] radio frequency=915.0 node=1 cs=D24 reset=D25 disabled",
        "[hw] sdcard mount=/sd cs=D26 disabled",
        "[hw] ir rx=[D11] emitters=line:D12 disabled",
    ]
    assert re.fullmatch(r"\[hw\] ready outputs=0 buttons=1 elapsed_s=\d+\.\d{3}", lines[-1])


def test_no_pixel_entries_narrate_no_pixel_lines():
    assert "pixels[" not in _narration(_config())


def test_the_current_budget_line_reports_limit_estimate_scale_and_strips_held_at_the_floor():
    # 100 px @ 1.0 + 100 px @ 0.2 at 60 mA/px is a 7200 mA estimate; the dim
    # strip is held at the 0.1 floor and the bright one scaled by 1400 / 6000.
    config = _config(
        pixels=[
            {**_NEOPIXEL, "count": 100, "scope_pixels": {"personal": [0, 100]}},
            {
                **_NEOPIXEL,
                "pin": "GP1",
                "count": 100,
                "brightness": 0.2,
                "scope_pixels": {"ambient": [0, 100]},
            },
        ],
        neopixel_current_budget={"current_limit_ma": 2000, "min_brightness": 0.1},
    )

    assert (
        "[hw] neopixel_current_budget limit=2000mA estimate=7200mA scale=0.23 at_min_brightness=1\n"
        in _narration(config)
    )


def test_a_disabled_pixel_entry_is_narrated_disabled():
    text = _narration(_config(pixels=[_disabled(_MATRIX)]))

    assert "[hw] pixels[0] matrix disabled\n" in text


def test_the_current_budget_is_reported_before_the_pixel_lines():
    config = _config(neopixel_current_budget={"current_limit_ma": 100}, pixels=[_NEOPIXEL])

    lines = _narration(config).splitlines()

    budget = next(i for i, line in enumerate(lines) if "neopixel_current_budget" in line)
    assert lines[budget + 1].startswith("[hw] pixels[0] neopixel")


@pytest.mark.parametrize(
    ("part", "config", "line"),
    [
        ("accelerometer", _config(accelerometer={}), "[hw] accelerometer lis3dh FAILED\n"),
        ("storage", _config(sdcard=_SDCARD), "[hw] sdcard mount=/sd cs=GP15 FAILED\n"),
        ("ir_writer", _config(ir=_IR), "[hw] ir rx=[GP5] emitters=line:GP6 FAILED\n"),
        ("button_reader", _config(buttons=["GP3"]), "[hw] buttons A=GP3 FAILED\n"),
        ("haptic_output", _config(haptics={}), "[hw] haptics drv2605 FAILED\n"),
    ],
    ids=["accelerometer", "storage", "ir_writer", "button_reader", "haptic_output"],
)
def test_a_part_that_raises_fails_its_own_line_and_propagates(part, config, line):
    fragments: list[str] = []
    logger = Logger("[hw]", fragments.append)

    with pytest.raises(PartError):
        assemble_device(config, RecordingParts(fail_on=part), logger)

    assert "".join(fragments).endswith(line)


def test_a_missing_bus_fails_the_line_of_the_section_needing_it():
    fragments: list[str] = []

    with pytest.raises(RuntimeError):
        assemble_device(
            _config(haptics={}), RecordingParts(no_i2c=True), Logger("[hw]", fragments.append)
        )

    assert "".join(fragments).endswith("[hw] haptics drv2605 FAILED\n")


def test_without_a_logger_the_assembly_is_silent(capsys):
    _assemble(_config(buttons=["GP3"]))

    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------


def test_each_button_pin_is_read_with_its_field_in_declared_order():
    _hw, parts = _assemble(_config(buttons=["GP3", "GP7"]))

    assert parts.args_of("button_reader") == [
        (PinRef("GP3", "buttons[0]"),),
        (PinRef("GP7", "buttons[1]"),),
    ]


def test_buttons_are_labelled_a_onward_in_declared_order_over_their_pins():
    hw, parts = _assemble(_config(buttons=["GP3", "GP7"]))
    parts.pin_levels["GP7"] = False  # pulled low: pressed
    out = ButtonData(states={})

    hw.buttons.update(0.5, out)

    assert (out.is_pressed("A"), out.is_pressed("B")) == (False, True)


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------


def test_a_single_ir_receiver_is_read_on_ir_rx():
    _hw, parts = _assemble(_config(ir=_IR))

    assert parts.args_of("ir_reader") == [(PinRef("GP5", "ir.rx"),)]


def test_several_ir_receivers_are_read_on_indexed_fields():
    _hw, parts = _assemble(_config(ir={"rx": ["GP5", "GP8"], "line": "GP6"}))

    assert parts.args_of("ir_reader") == [
        (PinRef("GP5", "ir.rx[0]"),),
        (PinRef("GP8", "ir.rx[1]"),),
    ]


def test_emitters_are_built_in_ir_emitters_order_with_their_fields():
    ir = {"rx": "GP5", "area_of_effect": "GP9", "line": "GP6", "cone": "GP7"}

    _hw, parts = _assemble(_config(ir=ir))

    assert parts.args_of("ir_writer") == [
        (LINE, PinRef("GP6", "ir.line")),
        (CONE, PinRef("GP7", "ir.cone")),
        (AREA_OF_EFFECT, PinRef("GP9", "ir.area_of_effect")),
    ]


def test_an_ir_send_reaches_the_writer_of_its_emitter():
    hw, parts = _assemble(_config(ir={"rx": "GP5", "line": "GP6", "cone": "GP7"}))

    hw.network_controls.send_ir(b"\x01", CONE)

    assert [bool(parts.writers[e].written) for e in (LINE, CONE)] == [False, True]


def test_ir_with_no_emitters_narrates_plain_ok():
    assert "[hw] ir rx=[GP5] emitters=(none) ok\n" in _narration(_config(ir={"rx": "GP5"}))


# ---------------------------------------------------------------------------
# Radio and network controls
# ---------------------------------------------------------------------------


def test_the_radio_transport_is_built_on_the_spi_bus_with_its_pins():
    _hw, parts = _assemble(_config(radio=_RADIO))

    ((radio_config, bus, cs, reset),) = parts.args_of("radio_transport")
    assert (radio_config.node, bus.kind, cs, reset) == (
        3,
        "spi",
        PinRef("GP13", "radio.cs"),
        PinRef("GP14", "radio.reset"),
    )


def test_a_radio_send_through_the_network_controls_reaches_the_transport():
    hw, parts = _assemble(_config(radio=_RADIO))
    assert isinstance(hw.radio, RadioTransceiver)

    hw.network_controls.send_radio(b"ping")

    assert [transport.sent for transport in parts.transports] == [[b"ping"]]


def test_without_ir_the_network_controls_cannot_send_ir():
    hw, _parts = _assemble(_config())

    with pytest.raises(ValueError, match="line"):
        hw.network_controls.send_ir(b"\x01", LINE)


# ---------------------------------------------------------------------------
# DeviceHardware
# ---------------------------------------------------------------------------


def test_outputs_are_pixels_then_audio_then_haptics():
    hw, _parts = _assemble(_config(pixels=[_NEOPIXEL], audio=_AUDIO, haptics={}))

    assert [cast(Output, output).part for output in hw.outputs] == [
        "neopixel_strip",
        "audio_output",
        "haptic_output",
    ]


def test_the_audio_output_is_built_on_the_configured_i2s_pins():
    _hw, parts = _assemble(_config(audio=_AUDIO))

    ((_audio, *pins),) = parts.args_of("audio_output")
    assert pins == [
        PinRef("GP10", "audio.i2s_bit_clock"),
        PinRef("GP11", "audio.i2s_word_select"),
        PinRef("GP12", "audio.i2s_data"),
    ]


def test_storage_is_what_the_storage_part_built_on_the_spi_bus():
    hw, parts = _assemble(_config(sdcard=_SDCARD))

    ((_sdcard, bus, cs),) = parts.args_of("storage")
    assert (bus.kind, cs) == ("spi", PinRef("GP15", "sdcard.cs"))
    assert hw.storage is not None and hw.storage.mount_root == "/sd"


def test_a_bare_config_builds_no_optional_hardware():
    hw, _parts = _assemble(_config())

    assert (
        hw.outputs,
        hw.accelerometer,
        hw.magnetometer,
        hw.ir,
        hw.radio,
        hw.storage,
    ) == ([], None, None, None, None, None)
