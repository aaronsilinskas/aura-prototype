"""Stub CircuitPython-only hardware modules so the hardware code imports under CPython for tests."""

import sys
import types


def _fake_module(name: str, **attrs: object) -> types.ModuleType:
    """Build a module named ``name`` holding ``attrs``, without registering it."""
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    return module


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

sys.modules.setdefault("microcontroller", _fake_module("microcontroller", Pin=type("Pin", (), {})))

_board = sys.modules["board"]

# ---------------------------------------------------------------------------
# adafruit_is31fl3741 stub — minimal for circuitpython_parts imports
# ---------------------------------------------------------------------------

sys.modules.setdefault("adafruit_is31fl3741", _fake_module("adafruit_is31fl3741", MUST_BUFFER=1))
sys.modules.setdefault(
    "adafruit_is31fl3741.adafruit_rgbmatrixqt",
    _fake_module(
        "adafruit_is31fl3741.adafruit_rgbmatrixqt",
        Adafruit_RGBMatrixQT=type("Adafruit_RGBMatrixQT", (), {}),
    ),
)


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


sys.modules["adafruit_drv2605"] = _fake_module("adafruit_drv2605", Effect=_Effect, Pause=_Pause)


# ---------------------------------------------------------------------------
# adafruit_rfm69 stub — minimal RFM69 placeholder for Rfm69RadioTransport tests
# ---------------------------------------------------------------------------

sys.modules.setdefault(
    "adafruit_rfm69", _fake_module("adafruit_rfm69", RFM69=type("RFM69", (), {}))
)


# ---------------------------------------------------------------------------
# sdcardio / storage stubs -- minimal placeholders for SdCardStorage tests
# ---------------------------------------------------------------------------

sys.modules.setdefault("sdcardio", _fake_module("sdcardio", SDCard=type("SDCard", (), {})))
sys.modules.setdefault(
    "storage",
    _fake_module("storage", VfsFat=type("VfsFat", (), {}), mount=lambda *args, **kwargs: None),
)
