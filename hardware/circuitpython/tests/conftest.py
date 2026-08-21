"""Stub CircuitPython-only hardware modules so the hardware code imports under CPython for tests."""

import sys
import types

for _name in (
    "audiobusio",
    "audiocore",
    "audiomixer",
    "board",
    "busio",
    "digitalio",
    "neopixel",
    "pulseio",
):
    sys.modules.setdefault(_name, types.ModuleType(_name))

_microcontroller_mod = types.ModuleType("microcontroller")
_microcontroller_mod.Pin = type("Pin", (), {})  # type: ignore[attr-defined]
_microcontroller_mod.reset = lambda: None  # type: ignore[attr-defined]
sys.modules.setdefault("microcontroller", _microcontroller_mod)

_board = sys.modules["board"]

# ---------------------------------------------------------------------------
# adafruit_is31fl3741 stub — minimal for device_builder imports
# ---------------------------------------------------------------------------

_is31_mod = types.ModuleType("adafruit_is31fl3741")
_is31_mod.MUST_BUFFER = 1  # type: ignore[attr-defined]
sys.modules.setdefault("adafruit_is31fl3741", _is31_mod)

_rgbmatrix_mod = types.ModuleType("adafruit_is31fl3741.adafruit_rgbmatrixqt")
_rgbmatrix_mod.Adafruit_RGBMatrixQT = type(  # type: ignore[attr-defined]
    "Adafruit_RGBMatrixQT", (), {}
)
sys.modules.setdefault("adafruit_is31fl3741.adafruit_rgbmatrixqt", _rgbmatrix_mod)


# ---------------------------------------------------------------------------
# adafruit_drv2605 stub — minimal Effect and Pause for Drv2605EffectOutput tests
# ---------------------------------------------------------------------------


class _Effect:
    """Minimal stub for adafruit_drv2605.Effect with equality comparison."""

    __slots__ = ("id",)

    def __init__(self, id: int) -> None:
        self.id = id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Effect):
            return self.id == other.id
        return NotImplemented

    def __repr__(self) -> str:
        return f"Effect({self.id})"


class _Pause:
    """Minimal stub for adafruit_drv2605.Pause with equality comparison."""

    __slots__ = ("duration",)

    def __init__(self, duration: int) -> None:
        self.duration = duration

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Pause):
            return self.duration == other.duration
        return NotImplemented

    def __repr__(self) -> str:
        return f"Pause({self.duration})"


_drv2605_mod = types.ModuleType("adafruit_drv2605")
_drv2605_mod.Effect = _Effect  # type: ignore[attr-defined]
_drv2605_mod.Pause = _Pause  # type: ignore[attr-defined]
sys.modules["adafruit_drv2605"] = _drv2605_mod


# ---------------------------------------------------------------------------
# adafruit_rfm69 stub — minimal RFM69 placeholder for Rfm69RadioTransport tests
# ---------------------------------------------------------------------------

_rfm69_mod = types.ModuleType("adafruit_rfm69")
_rfm69_mod.RFM69 = type("RFM69", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("adafruit_rfm69", _rfm69_mod)


# ---------------------------------------------------------------------------
# sdcardio / storage stubs -- minimal placeholders for SdCardStorage tests
# ---------------------------------------------------------------------------

_sdcardio_mod = types.ModuleType("sdcardio")
_sdcardio_mod.SDCard = type("SDCard", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("sdcardio", _sdcardio_mod)

_storage_mod = types.ModuleType("storage")
_storage_mod.VfsFat = type("VfsFat", (), {})  # type: ignore[attr-defined]
_storage_mod.mount = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("storage", _storage_mod)
