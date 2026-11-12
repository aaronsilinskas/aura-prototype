"""The example ``aura-device.*.json`` files stay in sync with each other.

The simulated config stands in for real hardware in the Simulation test
harness, so every example must declare the same capabilities. Wiring (pins,
buses, addresses), the pixel layout, brightness, current budgets, and
``max_volume`` are free to differ.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.state import Scope
from hardware.shared.device_config import (
    DeviceConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    load_device_config,
)

_EXAMPLES = Path(__file__).resolve().parents[3] / "examples"
_EXAMPLE_CONFIGS = sorted(_EXAMPLES.glob("aura-device.*.json"))
_SIMULATED_CONFIG = _EXAMPLES / "aura-device.simulated.json"
_PICO_2_CONFIG = _EXAMPLES / "aura-device.pico-2.json"


def _pixel_scopes(config: DeviceConfig) -> set[str]:
    scopes: set[str] = set()
    for entry in config.pixels:
        if isinstance(entry, MatrixPixelsConfig):
            scopes.update(entry.scope_rows)
        else:
            scopes.update(entry.scopes)
            for strip in entry.strips:
                scopes.update(strip.scope_pixels)
    return scopes


def _capabilities(config: DeviceConfig) -> dict[str, object]:
    return {
        "buttons": len(config.buttons),
        "ir_emitters": set(config.ir.emitters) if config.ir else set(),
        "ir_receivers": len(config.ir.rx) if config.ir else 0,
        "audio": config.audio is not None and config.audio.enabled,
        "voices": config.audio.voices if config.audio else 0,
        "haptics": config.haptics is not None,
        "accelerometer": config.accelerometer is not None,
        "magnetometer": config.magnetometer is not None,
        "radio": config.radio is not None,
        "sdcard": config.sdcard is not None,
        "pixel_scopes": _pixel_scopes(config),
    }


def test_the_simulated_config_sits_alongside_a_real_one():
    assert _SIMULATED_CONFIG in _EXAMPLE_CONFIGS
    assert len(_EXAMPLE_CONFIGS) >= 2


@pytest.mark.parametrize("path", _EXAMPLE_CONFIGS, ids=lambda p: p.name)
def test_every_example_config_declares_the_simulated_devices_capabilities(path):
    expected = _capabilities(load_device_config(str(_SIMULATED_CONFIG)))

    assert _capabilities(load_device_config(str(path))) == expected


def test_the_simulated_config_lays_out_one_strip_per_scope_for_every_scope():
    config = load_device_config(str(_SIMULATED_CONFIG))

    strips = [
        strip
        for entry in config.pixels
        if isinstance(entry, NeoPixelPixelsConfig)
        for strip in entry.strips
    ]
    assert len(strips) == len(config.pixels)
    assert sorted(key for strip in strips for key in strip.scope_pixels) == sorted(Scope.ALL.keys)
    assert all(len(strip.scope_pixels) == 1 for strip in strips)


def test_the_pico_2_config_puts_the_enabled_radio_on_its_own_spi_bus_apart_from_the_sdcard():
    config = load_device_config(str(_PICO_2_CONFIG))

    assert config.radio is not None and config.radio.enabled
    assert config.sdcard is not None
    assert (config.radio.spi, config.sdcard.spi) == ("radio", "default")
    assert {
        name: (bus.sck.name, bus.mosi.name, bus.miso.name) for name, bus in config.spi.items()
    } == {
        "default": ("GP2", "GP3", "GP0"),
        "radio": ("GP14", "GP15", "GP12"),
    }


@pytest.mark.parametrize(
    ("path", "pins"),
    [(_PICO_2_CONFIG, ("GP4", "GP5")), (_SIMULATED_CONFIG, ("SIM_SDA", "SIM_SCL"))],
    ids=["pico-2", "simulated"],
)
def test_each_example_declares_one_default_i2c_bus_on_its_pins(path, pins):
    config = load_device_config(str(path))

    assert {name: (bus.sda.name, bus.scl.name) for name, bus in config.i2c.items()} == {
        "default": pins
    }
