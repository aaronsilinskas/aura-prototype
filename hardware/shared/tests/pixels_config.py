"""Narrow a parsed ``DeviceConfig``'s pixel entries to the variant a test expects.

A wrong variant fails the test's assertion instead of raising ``AttributeError``.
"""

from hardware.shared.device_config import (
    DeviceConfig,
    MatrixPixelsConfig,
    NeoPixelPixelsConfig,
    NeoPixelStripConfig,
)


def as_matrix(entry: MatrixPixelsConfig | NeoPixelPixelsConfig) -> MatrixPixelsConfig:
    assert isinstance(entry, MatrixPixelsConfig)
    return entry


def as_neopixel(entry: MatrixPixelsConfig | NeoPixelPixelsConfig) -> NeoPixelPixelsConfig:
    assert isinstance(entry, NeoPixelPixelsConfig)
    return entry


def first_strip(config: DeviceConfig, entry: int = 0) -> NeoPixelStripConfig:
    """The first strip of *config*'s pixel entry at *entry*, which must be a NeoPixel."""
    return as_neopixel(config.pixels[entry]).strips[0]
