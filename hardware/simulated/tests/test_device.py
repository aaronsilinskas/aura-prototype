"""The Simulated device takes its hardware shape from a ``DeviceConfig``."""

from __future__ import annotations

import pytest

from engine.input import ButtonData
from engine.state import Scope
from hardware.shared.device_config import DeviceConfig, parse_device_config
from hardware.simulated.device import SimulatedHardware


def _config(**sections: object) -> DeviceConfig:
    return parse_device_config(
        {
            "pixels": [
                {
                    "type": "neopixel",
                    "pin": "P0",
                    "count": 4,
                    "scope_pixels": {"personal": [0, 4]},
                },
                {
                    "type": "neopixel",
                    "pin": "P1",
                    "count": 7,
                    "scope_pixels": {"directional": [0, 7]},
                },
            ],
            **sections,
        }
    )


def _read_buttons(sim_hw: SimulatedHardware) -> ButtonData:
    """Apply due pin changes, then read the buttons once a debounce interval has passed."""
    out = ButtonData(states={})
    sim_hw.settle_pins()
    sim_hw.hw.buttons.update(0.5, out)
    return out


def test_each_scope_strip_is_as_long_as_its_configured_segment():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    assert sim_hw.strip(Scope.PERSONAL).size == 4
    assert sim_hw.strip(Scope.DIRECTIONAL).size == 7


def test_a_scope_strip_starts_dark():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config())

    assert sim_hw.strip(Scope.PERSONAL).dark


def test_buttons_are_labelled_a_onward_one_per_configured_pin():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(buttons=["X", "Y", "Z"]))

    sim_hw.hold("C")
    out = _read_buttons(sim_hw)

    assert out.is_pressed("C")


def test_a_button_the_config_does_not_declare_cannot_be_held():
    sim_hw = SimulatedHardware(now=lambda: 0.0, config=_config(buttons=["X"]))

    with pytest.raises(KeyError):
        sim_hw.hold("B")


def test_a_matrix_pixel_entry_is_rejected():
    config = parse_device_config(
        {"pixels": [{"type": "matrix", "cols": 13, "scope_rows": {"personal": [0, 1]}}]}
    )

    with pytest.raises(ValueError, match="matrix"):
        SimulatedHardware(now=lambda: 0.0, config=config)
