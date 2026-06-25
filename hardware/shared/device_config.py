"""Pure config parser for aura-device.json — no board imports, CPython-testable."""

from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

from engine.state import Scope

__all__ = [
    "DEFAULT_DEVICE_CONFIG",
    "DeviceConfig",
    "MatrixPixelsConfig",
    "NeoPixelPixelsConfig",
    "NeoPixelScopeConfig",
    "parse_device_config",
    "validate_band_map",
]

# ---------------------------------------------------------------------------
# Valid key sets
# ---------------------------------------------------------------------------

_VALID_SCOPE_KEYS: Final = set(Scope.ALL.keys)

_VALID_IR_EMITTER_KEYS: Final = {"line", "cone", "area_of_effect"}

# ---------------------------------------------------------------------------
# Default mapping — stock PropMaker + IS31FL3741 matrix
# ---------------------------------------------------------------------------

DEFAULT_DEVICE_CONFIG: Final = {
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


# ---------------------------------------------------------------------------
# Config data classes
# ---------------------------------------------------------------------------


class MatrixPixelsConfig:
    """Parsed matrix pixels configuration."""

    __slots__ = ("cols", "scope_rows")

    def __init__(self, cols: int, scope_rows: dict[str, range]) -> None:
        self.cols: int = cols
        self.scope_rows: dict[str, range] = scope_rows


class NeoPixelScopeConfig:
    """Parsed NeoPixel scope configuration."""

    __slots__ = ("brightness", "count", "order", "pin")

    def __init__(self, pin: str, count: int, order: str, brightness: float) -> None:
        self.pin: str = pin
        self.count: int = count
        self.order: str = order
        self.brightness: float = brightness


class NeoPixelPixelsConfig:
    """Parsed NeoPixel pixels configuration."""

    __slots__ = ("scopes",)

    def __init__(self, scopes: dict[str, NeoPixelScopeConfig]) -> None:
        self.scopes: dict[str, NeoPixelScopeConfig] = scopes


class AudioConfig:
    """Parsed audio configuration."""

    __slots__ = ("clips", "max_volume", "voices")

    def __init__(self, voices: int, max_volume: float, clips: dict[str, str]) -> None:
        self.voices: int = voices
        self.max_volume: float = max_volume
        self.clips: dict[str, str] = clips


class IRConfig:
    """Parsed IR configuration."""

    __slots__ = ("emitters", "rx")

    def __init__(self, rx: str, emitters: dict[str, str]) -> None:
        self.rx: str = rx
        self.emitters: dict[str, str] = emitters


class DeviceConfig:
    """Parsed device configuration produced by parse_device_config."""

    __slots__ = ("audio", "buttons", "ir", "pixels")

    def __init__(
        self,
        pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig],
        buttons: list[str],
        ir: IRConfig | None,
        audio: AudioConfig | None,
    ) -> None:
        self.pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig] = pixels
        self.buttons: list[str] = buttons
        self.ir: IRConfig | None = ir
        self.audio: AudioConfig | None = audio


# ---------------------------------------------------------------------------
# Band-map validator (shared)
# ---------------------------------------------------------------------------


def validate_band_map(bands: dict[str, range], context: str) -> None:
    """Validate that all scope keys are valid and bands do not overlap.

    Args:
        bands: Mapping of scope key → range.
        context: Label used in error messages (e.g. ``"pixels[0].scope_rows"``).

    Raises:
        ValueError: If a key is invalid or two bands overlap.
    """
    for key in bands:
        if key not in _VALID_SCOPE_KEYS:
            valid = ", ".join(sorted(_VALID_SCOPE_KEYS))
            raise ValueError(f"{context} key '{key}' is not valid; valid keys: {valid}")

    items = list(bands.items())
    for i in range(len(items)):
        ka, ra = items[i]
        for j in range(i + 1, len(items)):
            kb, rb = items[j]
            if ra.start < rb.stop and rb.start < ra.stop:
                raise ValueError(
                    f"{context}: bands '{ka}' ({ra.start}-{ra.stop}) and "
                    f"'{kb}' ({rb.start}-{rb.stop}) overlap"
                )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _parse_matrix_pixels(mapping: dict, entry_index: int) -> MatrixPixelsConfig:
    label = f"pixels[{entry_index}]"
    if "cols" not in mapping:
        raise ValueError(f"{label}.cols is required for matrix type")
    if "scope_rows" not in mapping:
        raise ValueError(f"{label}.scope_rows is required for matrix type")

    cols = mapping["cols"]
    raw_scope_rows = mapping["scope_rows"]

    scope_rows: dict[str, range] = {}
    for key, value in raw_scope_rows.items():
        scope_rows[key] = range(value[0], value[1])

    validate_band_map(scope_rows, f"{label}.scope_rows")

    return MatrixPixelsConfig(cols=cols, scope_rows=scope_rows)


def _parse_neopixel_pixels(mapping: dict) -> NeoPixelPixelsConfig:
    scopes_raw = mapping.get("scopes", {})
    scopes: dict[str, NeoPixelScopeConfig] = {}

    for key, scope_cfg in scopes_raw.items():
        if key not in _VALID_SCOPE_KEYS:
            valid = ", ".join(sorted(_VALID_SCOPE_KEYS))
            raise ValueError(f"pixels.scopes key '{key}' is not valid; valid keys: {valid}")
        if "pin" not in scope_cfg:
            raise ValueError(f"pixels.scopes.{key}.pin is required")
        if not isinstance(scope_cfg["pin"], str):
            raise ValueError(f"pixels.scopes.{key}.pin must be a string pin name")
        if "count" not in scope_cfg:
            raise ValueError(f"pixels.scopes.{key}.count is required")
        scopes[key] = NeoPixelScopeConfig(
            pin=scope_cfg["pin"],
            count=scope_cfg["count"],
            order=scope_cfg.get("order", "GRB"),
            brightness=scope_cfg.get("brightness", 1.0),
        )

    return NeoPixelPixelsConfig(scopes=scopes)


def _parse_pixels_entry(
    mapping: dict, entry_index: int
) -> MatrixPixelsConfig | NeoPixelPixelsConfig:
    pixels_type = mapping.get("type")
    if pixels_type == "matrix":
        return _parse_matrix_pixels(mapping, entry_index)
    if pixels_type == "neopixel":
        return _parse_neopixel_pixels(mapping)
    raise ValueError(
        f"pixels[{entry_index}].type '{pixels_type}' is not valid; expected 'matrix' or 'neopixel'"
    )


def _parse_buttons(buttons_raw: list) -> list[str]:
    if not buttons_raw:
        raise ValueError("buttons requires at least one pin")
    result: list[str] = []
    for i, pin in enumerate(buttons_raw):
        if not isinstance(pin, str):
            raise ValueError(f"buttons[{i}] must be a string pin name, got {type(pin).__name__}")
        result.append(pin)
    return result


def _parse_ir(ir_raw: dict) -> IRConfig:
    if "rx" not in ir_raw:
        raise ValueError("ir.rx is required")
    if not isinstance(ir_raw["rx"], str):
        raise ValueError("ir.rx must be a string pin name")
    if "line" not in ir_raw:
        raise ValueError("ir.line is required")
    if not isinstance(ir_raw["line"], str):
        raise ValueError("ir.line must be a string pin name")

    emitters: dict[str, str] = {}
    for key, pin in ir_raw.items():
        if key == "rx":
            continue
        if key not in _VALID_IR_EMITTER_KEYS:
            valid = ", ".join(sorted(_VALID_IR_EMITTER_KEYS))
            raise ValueError(f"ir emitter key '{key}' is not valid; valid keys: {valid}")
        if not isinstance(pin, str):
            raise ValueError(f"ir.{key} must be a string pin name")
        emitters[key] = pin

    return IRConfig(rx=ir_raw["rx"], emitters=emitters)


def _parse_audio(audio_raw: dict) -> AudioConfig:
    voices = audio_raw.get("voices", 1)
    if not isinstance(voices, int) or voices < 1:
        raise ValueError("audio.voices must be a positive integer")
    max_volume = audio_raw.get("max_volume", 1.0)
    clips: dict[str, str] = dict(audio_raw.get("clips", {}))
    return AudioConfig(voices=voices, max_volume=max_volume, clips=clips)


def parse_device_config(mapping: dict) -> DeviceConfig:
    """Parse a device config mapping into a DeviceConfig.

    The ``pixels`` key must be a list of pixel-output entries.  Each entry
    must have a ``type`` field of ``"matrix"`` or ``"neopixel"``.  The list
    must contain at least one entry, and at most one entry of type
    ``"matrix"``.

    Example ``aura-device.json`` snippet::

        {
            "pixels": [
                {
                    "type": "matrix",
                    "cols": 13,
                    "scope_rows": {
                        "global.main": [2, 5],
                        "personal": [5, 7]
                    }
                }
            ],
            "buttons": ["D9", "D10"]
        }

    Raises:
        ValueError: If any required field is missing or invalid.
    """
    pixels_raw = mapping.get("pixels", [])

    if not isinstance(pixels_raw, list):
        raise ValueError("pixels must be a list of pixel-output entries")

    if len(pixels_raw) == 0:
        raise ValueError("pixels must contain at least one entry")

    pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig] = []
    matrix_count = 0
    for i, entry in enumerate(pixels_raw):
        parsed = _parse_pixels_entry(entry, i)
        if isinstance(parsed, MatrixPixelsConfig):
            matrix_count += 1
            if matrix_count > 1:
                raise ValueError(f"pixels[{i}]: only one matrix entry is allowed")
        pixels.append(parsed)

    buttons_raw = mapping.get("buttons", [])
    buttons = _parse_buttons(buttons_raw)

    ir: IRConfig | None = None
    if "ir" in mapping:
        ir = _parse_ir(mapping["ir"])

    audio: AudioConfig | None = None
    if "audio" in mapping:
        audio = _parse_audio(mapping["audio"])

    return DeviceConfig(pixels=pixels, buttons=buttons, ir=ir, audio=audio)
