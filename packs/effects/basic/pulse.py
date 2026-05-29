from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.manager import EffectBuilder


def _scale_color(color: int, brightness: float) -> int:
    r = int(((color >> 16) & 0xFF) * brightness)
    g = int(((color >> 8) & 0xFF) * brightness)
    b = int((color & 0xFF) * brightness)
    return (r << 16) | (g << 8) | b


class PulseRenderer(EffectRenderer):
    """Animates all pixels through a four-phase brightness cycle.

    Phases (half-open intervals):
    - BRIGHTEN ``[0, _b_on)``: lerp from start color to end color
    - ON ``[_b_on, _b_darken)``: hold at end color
    - DARKEN ``[_b_darken, _b_off)``: lerp from end color back to start color
    - OFF ``[_b_off, _cycle_total)``: hold at start color

    A phase with duration ``0.0`` is silently skipped. ``_elapsed`` is
    accumulated each tick then wrapped via ``%`` to prevent float drift on
    long-running embedded devices.
    """

    __slots__ = [
        "_b_darken",
        "_b_off",
        "_b_on",
        "_current_color",
        "_cycle_total",
        "_elapsed",
        "_end_b",
        "_end_g",
        "_end_r",
        "_name",
        "_start_b",
        "_start_g",
        "_start_r",
    ]

    def __init__(
        self,
        name: str,
        start_color: int,
        end_color: int,
        brighten_duration: float,
        on_duration: float,
        darken_duration: float,
        off_duration: float,
    ) -> None:
        self._name = name
        self._start_r = (start_color >> 16) & 0xFF
        self._start_g = (start_color >> 8) & 0xFF
        self._start_b = start_color & 0xFF
        self._end_r = (end_color >> 16) & 0xFF
        self._end_g = (end_color >> 8) & 0xFF
        self._end_b = end_color & 0xFF
        self._b_on = brighten_duration
        self._b_darken = brighten_duration + on_duration
        self._b_off = brighten_duration + on_duration + darken_duration
        self._cycle_total = brighten_duration + on_duration + darken_duration + off_duration
        self._elapsed = 0.0
        self._current_color = start_color

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        self._elapsed += elapsed
        self._elapsed %= self._cycle_total
        elapsed = self._elapsed
        if elapsed < self._b_on:
            t = elapsed / self._b_on
            r = int(self._start_r + (self._end_r - self._start_r) * t)
            g = int(self._start_g + (self._end_g - self._start_g) * t)
            b = int(self._start_b + (self._end_b - self._start_b) * t)
            self._current_color = (r << 16) | (g << 8) | b
        elif elapsed < self._b_darken:
            self._current_color = (self._end_r << 16) | (self._end_g << 8) | self._end_b
        elif elapsed < self._b_off:
            darken_dur = self._b_off - self._b_darken
            t = (elapsed - self._b_darken) / darken_dur
            r = int(self._end_r + (self._start_r - self._end_r) * t)
            g = int(self._end_g + (self._start_g - self._end_g) * t)
            b = int(self._end_b + (self._start_b - self._end_b) * t)
            self._current_color = (r << 16) | (g << 8) | b
        else:
            self._current_color = (self._start_r << 16) | (self._start_g << 8) | self._start_b

    def render(self, output: PixelBuffer) -> None:
        color = self._current_color
        for i in range(len(output)):
            output[i] = color


class PulseBuilder(EffectBuilder):
    """Builds a :class:`PulseRenderer` from a ``RendererConfig``.

    Reads ``start_color`` (default ``0x000000``), ``end_color`` (default
    ``0xFFFFFF``), ``brighten_duration``, ``on_duration``, ``darken_duration``,
    and ``off_duration`` (all default ``0.5`` seconds) from options. Level
    brightness scaling is applied to both colors at build time using the same
    per-channel ``int(channel * level / 10.0)`` truncation as ``basic.solid``.

    Raises ``ValueError`` if any duration is negative or if all durations sum
    to zero.
    """

    def __call__(self, name: str, config: RendererConfig) -> PulseRenderer:
        opts = config.options
        start_color_raw = opts.get("start_color", 0x000000)
        end_color_raw = opts.get("end_color", 0xFFFFFF)
        brighten_duration = opts.get("brighten_duration", 0.5)
        on_duration = opts.get("on_duration", 0.5)
        darken_duration = opts.get("darken_duration", 0.5)
        off_duration = opts.get("off_duration", 0.5)

        if brighten_duration < 0 or on_duration < 0 or darken_duration < 0 or off_duration < 0:
            raise ValueError("Pulse durations must be non-negative")
        cycle_total = brighten_duration + on_duration + darken_duration + off_duration
        if cycle_total == 0.0:
            raise ValueError("At least one pulse phase duration must be non-zero")

        brightness = config.level / 10.0
        start_color = _scale_color(start_color_raw, brightness)
        end_color = _scale_color(end_color_raw, brightness)

        return PulseRenderer(
            name,
            start_color,
            end_color,
            brighten_duration,
            on_duration,
            darken_duration,
            off_duration,
        )


BUILD = PulseBuilder()
