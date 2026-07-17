"""Config loader and parser for aura-device.json — no board imports, CPython-testable."""

from __future__ import annotations

import json

try:
    from collections.abc import Callable
    from typing import Final
except ImportError:
    pass

from engine.state import Scope

__all__ = [
    "AccelerometerConfig",
    "DeviceConfig",
    "HapticsConfig",
    "I2CConfig",
    "MatrixPixelsConfig",
    "NeoPixelPixelsConfig",
    "NeoPixelScopeConfig",
    "NeoPixelStripConfig",
    "RadioConfig",
    "SPIConfig",
    "first_neopixel_pin",
    "load_device_config",
    "parse_device_config",
    "read_device_config_mapping",
    "require_pin",
    "validate_band_map",
]

# ---------------------------------------------------------------------------
# Valid key sets
# ---------------------------------------------------------------------------

_VALID_SCOPE_KEYS: Final = set(Scope.ALL.keys)

_VALID_IR_EMITTER_KEYS: Final = {"line", "cone", "area_of_effect"}

_I2S_PIN_FIELDS: Final = ("i2s_bit_clock", "i2s_word_select", "i2s_data")

_I2C_PIN_FIELDS: Final = ("sda", "scl")

_SPI_PIN_FIELDS: Final = ("sck", "mosi", "miso")

_RADIO_ALLOWED_KEYS: Final = ("cs", "reset", "frequency", "node", "enabled")

_RADIO_PIN_FIELDS: Final = ("cs", "reset")

# `DeviceConfig.isolate` derives its isolatable set from `DeviceConfig.__slots__`
# minus these -- i2c/spi are buses (infrastructure for the kept component, not
# competition with it) and buttons carries no `enabled` flag to isolate.
_ISOLATE_EXCLUDED_COMPONENTS: Final = ("i2c", "spi", "buttons")

# ---------------------------------------------------------------------------
# Config data classes
# ---------------------------------------------------------------------------


class MatrixPixelsConfig:
    """Parsed matrix pixels configuration."""

    __slots__ = ("brightness", "cols", "enabled", "scope_rows")

    def __init__(
        self,
        cols: int,
        scope_rows: dict[str, range],
        brightness: float = 1.0,
        enabled: bool = True,
    ) -> None:
        self.cols: int = cols
        self.scope_rows: dict[str, range] = scope_rows
        self.brightness: float = brightness
        self.enabled: bool = enabled


class NeoPixelScopeConfig:
    """Parsed NeoPixel scope configuration (legacy one-strip-per-scope shape)."""

    __slots__ = ("brightness", "count", "order", "pin")

    def __init__(self, pin: str, count: int, order: str, brightness: float) -> None:
        self.pin: str = pin
        self.count: int = count
        self.order: str = order
        self.brightness: float = brightness


class NeoPixelStripConfig:
    """Parsed NeoPixel strip configuration with scope_pixels segmentation.

    Each strip entry has a single physical pin, a total pixel count, optional
    order and brightness, and a ``scope_pixels`` mapping of scope key to a
    ``range`` of pixel indices ``[start, end)`` within the strip.
    """

    __slots__ = ("brightness", "count", "order", "pin", "scope_pixels")

    def __init__(
        self,
        pin: str,
        count: int,
        order: str,
        brightness: float,
        scope_pixels: dict[str, range],
    ) -> None:
        self.pin: str = pin
        self.count: int = count
        self.order: str = order
        self.brightness: float = brightness
        self.scope_pixels: dict[str, range] = scope_pixels


class NeoPixelPixelsConfig:
    """Parsed NeoPixel pixels configuration.

    ``strips`` holds one ``NeoPixelStripConfig`` per physical strip entry
    (new scope_pixels shape).  ``scopes`` holds the legacy one-strip-per-scope
    mapping and is populated only when parsing old-shape entries.
    """

    __slots__ = ("enabled", "scopes", "strips")

    def __init__(
        self,
        scopes: dict[str, NeoPixelScopeConfig] | None = None,
        strips: list[NeoPixelStripConfig] | None = None,
        enabled: bool = True,
    ) -> None:
        self.scopes: dict[str, NeoPixelScopeConfig] = scopes if scopes is not None else {}
        self.strips: list[NeoPixelStripConfig] = strips if strips is not None else []
        self.enabled: bool = enabled


class AudioConfig:
    """Parsed audio configuration."""

    __slots__ = (
        "clips",
        "enabled",
        "i2s_bit_clock",
        "i2s_data",
        "i2s_word_select",
        "max_volume",
        "voices",
    )

    def __init__(
        self,
        voices: int,
        max_volume: float,
        clips: dict[str, str],
        i2s_bit_clock: str,
        i2s_word_select: str,
        i2s_data: str,
        enabled: bool = True,
    ) -> None:
        self.voices: int = voices
        self.max_volume: float = max_volume
        self.clips: dict[str, str] = clips
        self.i2s_bit_clock: str = i2s_bit_clock
        self.i2s_word_select: str = i2s_word_select
        self.i2s_data: str = i2s_data
        self.enabled: bool = enabled


class IRConfig:
    """Parsed IR configuration.

    ``rx`` is always a non-empty list of one or more pin names, regardless of
    whether ``aura-device.json`` declared ``ir.rx`` as a single string (the
    single-receiver shape) or a list of strings (the multi-receiver shape) —
    callers deal with one representation either way.
    """

    __slots__ = ("emitters", "enabled", "rx")

    def __init__(self, rx: list[str], emitters: dict[str, str], enabled: bool = True) -> None:
        self.rx: list[str] = rx
        self.emitters: dict[str, str] = emitters
        self.enabled: bool = enabled


class I2CConfig:
    """Parsed I2C bus configuration.

    ``enabled`` is mutable so a profiler can flip it on an already-parsed
    config to isolate hardware without re-parsing. ``enabled=False`` means
    ``device_builder`` builds no I2C bus at all — distinct from an absent
    ``i2c`` section, which still defaults to the board's SCL/SDA pins.
    """

    __slots__ = ("enabled", "scl", "sda")

    def __init__(self, sda: str, scl: str, enabled: bool = True) -> None:
        self.sda: str = sda
        self.scl: str = scl
        self.enabled: bool = enabled


class SPIConfig:
    """Parsed shared SPI bus configuration.

    Mirrors ``I2CConfig``: ``sck``/``mosi``/``miso`` are required together
    when the ``spi`` section is present. ``enabled`` is mutable so a profiler
    can flip it on an already-parsed config to isolate hardware without
    re-parsing. Absent ``spi`` section means ``device_builder`` falls back to
    ``board.SPI()`` later; ``enabled=False`` builds no bus at all.
    """

    __slots__ = ("enabled", "miso", "mosi", "sck")

    def __init__(self, sck: str, mosi: str, miso: str, enabled: bool = True) -> None:
        self.sck: str = sck
        self.mosi: str = mosi
        self.miso: str = miso
        self.enabled: bool = enabled


class AccelerometerConfig:
    """Parsed accelerometer configuration. Presence alone gates the LIS3DH build
    (see ``device_builder``) — there are no configurable keys yet besides
    ``enabled``.

    ``enabled`` is mutable so a profiler can flip it on an already-parsed
    config to isolate hardware without re-parsing.
    """

    __slots__ = ("enabled",)

    def __init__(self, enabled: bool = True) -> None:
        self.enabled: bool = enabled


class RadioConfig:
    """Parsed RFM69 radio peripheral configuration.

    Consumes the shared SPI bus (see ``SPIConfig``). ``frequency`` (MHz) is
    board-variant-specific, so the parser only type-checks it — no fixed
    valid range. ``node`` is this device's id on the radio network, ``0``
    to ``254`` inclusive (``255`` is the RadioHead broadcast address).

    ``enabled`` is mutable so a profiler can flip it on an already-parsed
    config to isolate hardware without re-parsing. A radio declared and
    enabled while ``spi`` is disabled is a *builder*-time hard error, not
    checked here.
    """

    __slots__ = ("cs", "enabled", "frequency", "node", "reset")

    def __init__(
        self, cs: str, reset: str, frequency: float, node: int, enabled: bool = True
    ) -> None:
        self.cs: str = cs
        self.reset: str = reset
        self.frequency: float = frequency
        self.node: int = node
        self.enabled: bool = enabled


class HapticsConfig:
    """Parsed haptics configuration. Presence alone gates the DRV2605 build
    (see ``device_builder``) — there are no configurable keys yet besides
    ``enabled``.

    ``enabled`` is mutable so a profiler can flip it on an already-parsed
    config to isolate hardware without re-parsing.
    """

    __slots__ = ("enabled",)

    def __init__(self, enabled: bool = True) -> None:
        self.enabled: bool = enabled


def _disabled_copy(section: object) -> object:
    """Return a copy of *section* with ``enabled`` forced to ``False``.

    Reads every name in *section*'s ``__slots__`` off the instance via
    ``getattr`` and passes them back as constructor keyword arguments,
    overriding only ``enabled``. One implementation serves every isolatable
    section class today because each of their ``__slots__`` tuples names
    exactly its constructor's keyword arguments; a future class that breaks
    that correspondence raises ``TypeError`` here instead of silently
    dropping a field, which a per-class copy method would risk. Precedent:
    ``ir_transport`` builds ``IrTelemetrySnapshot`` the same way, by
    splatting slot-driven ``getattr`` reads.

    Args:
        section: A parsed, non-``None`` section instance (e.g. an
            ``AudioConfig`` or a ``MatrixPixelsConfig``/``NeoPixelPixelsConfig``
            pixels-list entry).

    Returns:
        A new instance of ``type(section)`` equal to *section* on every
        slot except ``enabled``, which is ``False``.
    """
    kwargs = {name: getattr(section, name) for name in section.__slots__}
    kwargs["enabled"] = False
    return type(section)(**kwargs)


class DeviceConfig:
    """Parsed device configuration produced by parse_device_config."""

    __slots__ = (
        "accelerometer",
        "audio",
        "buttons",
        "haptics",
        "i2c",
        "ir",
        "pixels",
        "radio",
        "spi",
    )

    def __init__(
        self,
        pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig],
        buttons: list[str],
        ir: IRConfig | None,
        audio: AudioConfig | None,
        i2c: I2CConfig | None,
        accelerometer: AccelerometerConfig | None,
        haptics: HapticsConfig | None,
        spi: SPIConfig | None,
        radio: RadioConfig | None,
    ) -> None:
        self.pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig] = pixels
        self.buttons: list[str] = buttons
        self.ir: IRConfig | None = ir
        self.audio: AudioConfig | None = audio
        self.i2c: I2CConfig | None = i2c
        self.accelerometer: AccelerometerConfig | None = accelerometer
        self.haptics: HapticsConfig | None = haptics
        self.spi: SPIConfig | None = spi
        self.radio: RadioConfig | None = radio

    def isolate(self, keep: str) -> DeviceConfig:
        """Return a derived config with every isolatable component but *keep* disabled.

        Nothing re-parses: the returned config is built entirely from this
        already-parsed one. *keep* is left exactly as declared, including its
        own ``enabled`` value -- isolating a component declared
        ``enabled: false`` yields a config that builds nothing; ``isolate``
        is a way to narrow, never to force something on. Every other
        isolatable component is retained, not dropped: its section stays
        present with ``enabled`` forced to ``False``, the same shape
        ``parse_device_config`` already produces for a declared-but-disabled
        section. A component that is absent on this config is a no-op --
        it stays absent. ``i2c``, ``spi``, and ``buttons`` are never touched:
        buses are infrastructure for the kept component, not competition
        with it.

        The isolatable set is ``DeviceConfig.__slots__`` minus
        ``_ISOLATE_EXCLUDED_COMPONENTS``, so a component section added later
        is isolatable with no edit here.

        Args:
            keep: The one isolatable component to leave untouched, e.g.
                ``"audio"``.

        Raises:
            ValueError: If *keep* is not one of the isolatable components,
                naming the valid choices, sorted.
        """
        isolatable = sorted(set(self.__slots__) - set(_ISOLATE_EXCLUDED_COMPONENTS))
        if keep not in isolatable:
            valid = ", ".join(isolatable)
            raise ValueError(f"isolate keep '{keep}' is not valid; valid choices: {valid}")

        kwargs = {}
        for name in self.__slots__:
            value = getattr(self, name)
            if name in _ISOLATE_EXCLUDED_COMPONENTS or name == keep:
                kwargs[name] = value
            elif name == "pixels":
                kwargs[name] = [_disabled_copy(entry) for entry in value]
            elif value is None:
                kwargs[name] = None
            else:
                kwargs[name] = _disabled_copy(value)
        return DeviceConfig(**kwargs)


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
                    f"{context}: bands '{ka}' ({ra.start}-{ra.stop})"
                    + f" and '{kb}' ({rb.start}-{rb.stop}) overlap"
                )


# ---------------------------------------------------------------------------
# Brightness validator (shared across matrix, strip, and legacy scope entries)
# ---------------------------------------------------------------------------


def _parse_brightness(mapping: dict, key: str, field: str) -> float:
    """Return the brightness value at *key* in *mapping*, defaulting to 1.0.

    Args:
        mapping: The raw config mapping to read *key* from.
        key: The mapping key holding the brightness value (e.g. ``"brightness"``).
        field: Label used in error messages (e.g. ``"pixels[0].brightness"``).

    Raises:
        ValueError: If present but non-numeric or outside the inclusive
            ``[0.0, 1.0]`` range, naming *field*.
    """
    if key not in mapping:
        return 1.0

    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number in [0.0, 1.0], got {value!r}")
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{field} must be in [0.0, 1.0], got {value}")
    return float(value)


# ---------------------------------------------------------------------------
# Enabled validator (shared across ir, audio, i2c, accelerometer, haptics,
# and every pixels-list entry)
# ---------------------------------------------------------------------------


def _parse_enabled(mapping: dict, field: str) -> bool:
    """Return ``mapping["enabled"]``, defaulting to ``True`` when absent.

    Args:
        mapping: The raw config mapping to read the ``enabled`` key from.
        field: Label used in error messages (e.g. ``"accelerometer.enabled"``).

    Raises:
        ValueError: If present but not a ``bool``, naming *field*.
    """
    if "enabled" not in mapping:
        return True
    value = mapping["enabled"]
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean, got {value!r}")
    return value


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
    brightness = _parse_brightness(mapping, "brightness", f"{label}.brightness")
    enabled = _parse_enabled(mapping, f"{label}.enabled")

    scope_rows: dict[str, range] = {}
    for key, value in raw_scope_rows.items():
        scope_rows[key] = range(value[0], value[1])

    validate_band_map(scope_rows, f"{label}.scope_rows")

    return MatrixPixelsConfig(
        cols=cols, scope_rows=scope_rows, brightness=brightness, enabled=enabled
    )


def _parse_neopixel_strip_entry(mapping: dict, entry_index: int) -> NeoPixelStripConfig:
    label = f"pixels[{entry_index}]"

    if "pin" not in mapping:
        raise ValueError(f"{label}.pin is required for neopixel type")
    if "count" not in mapping:
        raise ValueError(f"{label}.count is required for neopixel type")

    pin: str = mapping["pin"]
    count: int = mapping["count"]
    order: str = mapping.get("order", "GRB")
    brightness: float = _parse_brightness(mapping, "brightness", f"{label}.brightness")

    scope_pixels_raw = mapping.get("scope_pixels")
    if not scope_pixels_raw:
        raise ValueError(
            f"{label}.scope_pixels is required and must be non-empty for neopixel type"
        )

    scope_pixels: dict[str, range] = {}
    for key, value in scope_pixels_raw.items():
        if key not in _VALID_SCOPE_KEYS:
            valid = ", ".join(sorted(_VALID_SCOPE_KEYS))
            raise ValueError(f"{label}.scope_pixels key '{key}' is not valid; valid keys: {valid}")
        start, end = value[0], value[1]
        if not (0 <= start < end <= count):
            msg = (
                f"{label} pin '{pin}' scope '{key}': segment [{start}, {end}] is out of range"
                + f" for strip count {count} (requires 0 <= start < end <= count)"
            )
            raise ValueError(msg)
        scope_pixels[key] = range(start, end)

    validate_band_map(scope_pixels, f"{label} pin '{pin}' scope_pixels")

    return NeoPixelStripConfig(
        pin=pin,
        count=count,
        order=order,
        brightness=brightness,
        scope_pixels=scope_pixels,
    )


def _parse_neopixel_pixels(mapping: dict, entry_index: int) -> NeoPixelPixelsConfig:
    label = f"pixels[{entry_index}]"
    enabled = _parse_enabled(mapping, f"{label}.enabled")

    if "scope_pixels" in mapping or "pin" in mapping:
        strip = _parse_neopixel_strip_entry(mapping, entry_index)
        return NeoPixelPixelsConfig(strips=[strip], enabled=enabled)

    # Legacy shape: scopes dict
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
        brightness = _parse_brightness(scope_cfg, "brightness", f"pixels.scopes.{key}.brightness")
        scopes[key] = NeoPixelScopeConfig(
            pin=scope_cfg["pin"],
            count=scope_cfg["count"],
            order=scope_cfg.get("order", "GRB"),
            brightness=brightness,
        )

    return NeoPixelPixelsConfig(scopes=scopes, enabled=enabled)


def _parse_pixels_entry(
    mapping: dict, entry_index: int
) -> MatrixPixelsConfig | NeoPixelPixelsConfig:
    pixels_type = mapping.get("type")
    if pixels_type == "matrix":
        return _parse_matrix_pixels(mapping, entry_index)
    if pixels_type == "neopixel":
        return _parse_neopixel_pixels(mapping, entry_index)
    raise ValueError(
        f"pixels[{entry_index}].type '{pixels_type}' is not valid; expected 'matrix' or 'neopixel'"
    )


def _parse_buttons(buttons_raw: list) -> list[str]:
    result: list[str] = []
    for i, pin in enumerate(buttons_raw):
        if not isinstance(pin, str):
            raise ValueError(f"buttons[{i}] must be a string pin name, got {type(pin).__name__}")
        result.append(pin)
    return result


def _parse_ir_rx(rx_raw: object) -> list[str]:
    """Normalize ``ir.rx`` to a non-empty list of pin names.

    Accepts either shape declared in ``aura-device.json``: a single pin-name
    string (today's single-receiver shape, normalized to a one-element list)
    or a non-empty list of pin-name strings (the multi-receiver shape,
    order preserved).

    Raises:
        ValueError: If *rx_raw* is an empty list, a list containing a
            non-string entry (naming its index), or neither a string nor a
            list.
    """
    if isinstance(rx_raw, str):
        return [rx_raw]

    if isinstance(rx_raw, list):
        if not rx_raw:
            raise ValueError("ir.rx must not be an empty list")
        result: list[str] = []
        for i, pin in enumerate(rx_raw):
            if not isinstance(pin, str):
                raise ValueError(f"ir.rx[{i}] must be a string pin name, got {type(pin).__name__}")
            result.append(pin)
        return result

    raise ValueError("ir.rx must be a string pin name or a list of string pin names")


def _parse_ir(ir_raw: dict) -> IRConfig:
    if "rx" not in ir_raw:
        raise ValueError("ir.rx is required")
    rx = _parse_ir_rx(ir_raw["rx"])

    # rx is the only required IR pin; every emitter (line/cone/area_of_effect)
    # is optional and validated uniformly by the loop below. A prop that
    # cannot transmit on a given emitter simply omits it; usage sites guard
    # the absence via require_pin.
    emitters: dict[str, str] = {}
    for key, pin in ir_raw.items():
        if key in ("rx", "enabled"):
            continue
        if key not in _VALID_IR_EMITTER_KEYS:
            valid = ", ".join(sorted(_VALID_IR_EMITTER_KEYS))
            raise ValueError(f"ir emitter key '{key}' is not valid; valid keys: {valid}")
        if not isinstance(pin, str):
            raise ValueError(f"ir.{key} must be a string pin name")
        emitters[key] = pin

    enabled = _parse_enabled(ir_raw, "ir.enabled")
    return IRConfig(rx=rx, emitters=emitters, enabled=enabled)


def _parse_audio(audio_raw: dict) -> AudioConfig:
    voices = audio_raw.get("voices", 1)
    if not isinstance(voices, int) or voices < 1:
        raise ValueError("audio.voices must be a positive integer")
    max_volume = audio_raw.get("max_volume", 1.0)
    clips: dict[str, str] = dict(audio_raw.get("clips", {}))

    # The I2S bus pins are required-together: a half-configured bus is exactly
    # the case where two of three might be missing, so every missing field is
    # named in one error instead of stopping at the first.
    missing = [field for field in _I2S_PIN_FIELDS if field not in audio_raw]
    if missing:
        names = ", ".join(f"audio.{field}" for field in missing)
        raise ValueError(f"{names} required together when audio section is present")

    for field in _I2S_PIN_FIELDS:
        if not isinstance(audio_raw[field], str):
            raise ValueError(f"audio.{field} must be a string pin name")

    enabled = _parse_enabled(audio_raw, "audio.enabled")
    return AudioConfig(
        voices=voices,
        max_volume=max_volume,
        clips=clips,
        i2s_bit_clock=audio_raw["i2s_bit_clock"],
        i2s_word_select=audio_raw["i2s_word_select"],
        i2s_data=audio_raw["i2s_data"],
        enabled=enabled,
    )


def _reject_unknown_keys(raw: dict, section: str, allowed: tuple[str, ...] = ()) -> None:
    # Minimal shape is {} plus whatever *allowed* names (e.g. "enabled") --
    # any other key present is unknown.
    for key in raw:
        if key in allowed:
            continue
        if allowed:
            valid = ", ".join(allowed)
            raise ValueError(f"{section}.{key} is not a valid key; {section} allows: {valid}")
        raise ValueError(f"{section}.{key} is not a valid key; {section} has no keys")


def _parse_accelerometer(accelerometer_raw: dict) -> AccelerometerConfig:
    _reject_unknown_keys(accelerometer_raw, "accelerometer", allowed=("enabled",))
    enabled = _parse_enabled(accelerometer_raw, "accelerometer.enabled")
    return AccelerometerConfig(enabled=enabled)


def _parse_haptics(haptics_raw: dict) -> HapticsConfig:
    _reject_unknown_keys(haptics_raw, "haptics", allowed=("enabled",))
    enabled = _parse_enabled(haptics_raw, "haptics.enabled")
    return HapticsConfig(enabled=enabled)


def _parse_i2c(i2c_raw: dict) -> I2CConfig:
    # sda/scl are required-together, mirroring the audio I2S bus pins: a
    # half-configured bus is exactly the case where one might be missing, so
    # every missing field is named in one error instead of stopping at the
    # first.
    missing = [field for field in _I2C_PIN_FIELDS if field not in i2c_raw]
    if missing:
        names = ", ".join(f"i2c.{field}" for field in missing)
        raise ValueError(f"{names} required together when i2c section is present")

    for field in _I2C_PIN_FIELDS:
        if not isinstance(i2c_raw[field], str):
            raise ValueError(f"i2c.{field} must be a string pin name")

    enabled = _parse_enabled(i2c_raw, "i2c.enabled")
    return I2CConfig(sda=i2c_raw["sda"], scl=i2c_raw["scl"], enabled=enabled)


def _parse_spi(spi_raw: dict) -> SPIConfig:
    # sck/mosi/miso are required-together, mirroring the i2c sda/scl pins: a
    # half-configured bus is exactly the case where one or two might be
    # missing, so every missing field is named in one error instead of
    # stopping at the first.
    missing = [field for field in _SPI_PIN_FIELDS if field not in spi_raw]
    if missing:
        names = ", ".join(f"spi.{field}" for field in missing)
        raise ValueError(f"{names} required together when spi section is present")

    for field in _SPI_PIN_FIELDS:
        if not isinstance(spi_raw[field], str):
            raise ValueError(f"spi.{field} must be a string pin name")

    enabled = _parse_enabled(spi_raw, "spi.enabled")
    return SPIConfig(
        sck=spi_raw["sck"], mosi=spi_raw["mosi"], miso=spi_raw["miso"], enabled=enabled
    )


def _parse_radio(radio_raw: dict) -> RadioConfig:
    _reject_unknown_keys(radio_raw, "radio", allowed=_RADIO_ALLOWED_KEYS)

    for field in _RADIO_PIN_FIELDS:
        if field not in radio_raw:
            raise ValueError(f"radio.{field} is required")
        if not isinstance(radio_raw[field], str):
            raise ValueError(f"radio.{field} must be a string pin name")
    cs = radio_raw["cs"]
    reset = radio_raw["reset"]

    if "frequency" not in radio_raw:
        raise ValueError("radio.frequency is required")
    frequency = radio_raw["frequency"]
    if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
        raise ValueError(f"radio.frequency must be a number (MHz), got {frequency!r}")

    if "node" not in radio_raw:
        raise ValueError("radio.node is required")
    node = radio_raw["node"]
    if isinstance(node, bool) or not isinstance(node, int):
        raise ValueError(f"radio.node must be an integer in [0, 254], got {node!r}")
    if not (0 <= node <= 254):
        raise ValueError(f"radio.node must be in [0, 254], got {node}")

    enabled = _parse_enabled(radio_raw, "radio.enabled")
    return RadioConfig(cs=cs, reset=reset, frequency=float(frequency), node=node, enabled=enabled)


def parse_device_config(mapping: dict) -> DeviceConfig:
    """Parse a device config mapping into a DeviceConfig.

    The ``pixels`` key is optional; when absent or an empty list, the device
    declares zero pixel outputs and ``DeviceConfig.pixels`` is ``[]``. When
    present and non-empty, ``pixels`` must be a list of pixel-output entries,
    each with a ``type`` field of ``"matrix"`` or ``"neopixel"``, with at
    most one entry of type ``"matrix"``.

    The ``buttons`` key is likewise optional; when absent or an empty list,
    the device declares zero buttons and ``DeviceConfig.buttons`` is ``[]``.

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

    pixels: list[MatrixPixelsConfig | NeoPixelPixelsConfig] = []
    matrix_count = 0
    seen_pins: set[str] = set()
    for i, entry in enumerate(pixels_raw):
        parsed = _parse_pixels_entry(entry, i)
        if isinstance(parsed, MatrixPixelsConfig):
            matrix_count += 1
            if matrix_count > 1:
                raise ValueError(f"pixels[{i}]: only one matrix entry is allowed")
        elif isinstance(parsed, NeoPixelPixelsConfig):
            for strip in parsed.strips:
                if strip.pin in seen_pins:
                    raise ValueError(
                        f"pixels[{i}]: pin '{strip.pin}' is already used by another strip entry"
                    )
                seen_pins.add(strip.pin)
        pixels.append(parsed)

    buttons_raw = mapping.get("buttons", [])
    buttons = _parse_buttons(buttons_raw)

    ir: IRConfig | None = None
    if "ir" in mapping:
        ir = _parse_ir(mapping["ir"])

    audio: AudioConfig | None = None
    if "audio" in mapping:
        audio = _parse_audio(mapping["audio"])

    i2c: I2CConfig | None = None
    if "i2c" in mapping:
        i2c = _parse_i2c(mapping["i2c"])

    spi: SPIConfig | None = None
    if "spi" in mapping:
        spi = _parse_spi(mapping["spi"])

    radio: RadioConfig | None = None
    if "radio" in mapping:
        radio = _parse_radio(mapping["radio"])

    accelerometer: AccelerometerConfig | None = None
    if "accelerometer" in mapping:
        accelerometer = _parse_accelerometer(mapping["accelerometer"])

    haptics: HapticsConfig | None = None
    if "haptics" in mapping:
        haptics = _parse_haptics(mapping["haptics"])

    return DeviceConfig(
        pixels=pixels,
        buttons=buttons,
        ir=ir,
        audio=audio,
        i2c=i2c,
        accelerometer=accelerometer,
        haptics=haptics,
        spi=spi,
        radio=radio,
    )


def read_device_config_mapping(path: str = "aura-device.json") -> dict:
    """Return the raw config mapping from the JSON file at *path*.

    Returns the raw mapping, not a parsed :class:`DeviceConfig`, so callers can
    read keys ``parse_device_config`` ignores (e.g. the ``"scene"`` selector).

    Raises:
        RuntimeError: If *path* does not exist. The device has no built-in
            default config, so a config file must be deployed to the board.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except OSError:
        raise RuntimeError(f"{path} not found — deploy a device config to the board") from None


def load_device_config(path: str = "aura-device.json") -> DeviceConfig:
    """Read and parse *path* into a :class:`DeviceConfig`.

    Board-free pair of :func:`read_device_config_mapping` and
    :func:`parse_device_config`, so profilers and other CPython-side callers
    don't each duplicate it.

    Raises:
        RuntimeError: If *path* does not exist.
        ValueError: If *path*'s contents fail validation.
    """
    return parse_device_config(read_device_config_mapping(path))


# ---------------------------------------------------------------------------
# Pin-sourcing helpers — on-device profilers read individual pin names out of
# a parsed DeviceConfig, failing loudly when a pin they need isn't declared.
# ---------------------------------------------------------------------------


def require_pin(
    config: DeviceConfig, getter: Callable[[DeviceConfig], str], field_label: str
) -> str:
    """Return ``getter(config)``, raising a uniform error when it isn't declared.

    *config* is always a real, already-parsed :class:`DeviceConfig` — callers
    load it via a raising loader (:func:`load_device_config`), so there is no
    ``None`` case to handle here. Only the narrow tuple of "field absent"
    exceptions (``AttributeError``, ``IndexError``, ``KeyError``) is caught, so
    a real bug inside *getter* still propagates instead of being swallowed.

    Args:
        config: The parsed device config to read from.
        getter: Callable extracting one field, e.g. ``lambda c: c.ir.emitters["line"]``.
        field_label: Dotted config path used in the error message, e.g.
            ``"ir.line"`` or ``"buttons[0]"``.

    Raises:
        ValueError: If *getter* raises for an absent field or section.
    """
    try:
        return getter(config)
    except (AttributeError, IndexError, KeyError):
        raise ValueError(f"{field_label} not declared in aura-device.json") from None


def first_neopixel_pin(config: DeviceConfig) -> str:
    """Return the pin of the first NeoPixel-type entry in ``config.pixels``.

    Prefers the modern ``strips`` shape (``strips[0].pin``) over the legacy
    one-strip-per-scope ``scopes`` shape within each NeoPixel entry, and
    returns the first entry that has a pin either way.

    Raises:
        KeyError: If ``config.pixels`` has no NeoPixel entry with a pin, so
            this composes as the *getter* passed to :func:`require_pin` and
            surfaces the same "not declared" message as any other field.
    """
    for entry in config.pixels:
        if not isinstance(entry, NeoPixelPixelsConfig):
            continue
        if entry.strips:
            return entry.strips[0].pin
        if entry.scopes:
            return next(iter(entry.scopes.values())).pin
    raise KeyError("no NeoPixel pixel entry declared")
