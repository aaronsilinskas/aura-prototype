from effects.effect import Effect, EffectConfig
from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect


class PulseBuilder(EffectBuilder):
    """Builds a :class:`PulseEffect` wrapping a :class:`PulseLayer` from a ``EffectConfig``.

    Reads ``start_color`` (default ``0x000000``), ``end_color`` (default
    ``0xFFFFFF``), ``brighten_duration``, ``on_duration``, ``darken_duration``,
    and ``off_duration`` (all default ``0.5`` seconds) from options. Colors are
    stored raw and unscaled; the ``brightness`` option is silently ignored.
    Brightness is an output-level concern applied by ``MatrixEffectOutput`` at
    render time.

    Raises ``ValueError`` if any duration is negative or if all durations sum
    to zero.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        opts = config.options
        start_color = opts.get("start_color", 0x000000)
        end_color = opts.get("end_color", 0xFFFFFF)
        brighten_duration = opts.get("brighten_duration", 0.5)
        on_duration = opts.get("on_duration", 0.5)
        darken_duration = opts.get("darken_duration", 0.5)
        off_duration = opts.get("off_duration", 0.5)

        if brighten_duration < 0 or on_duration < 0 or darken_duration < 0 or off_duration < 0:
            raise ValueError("Pulse durations must be non-negative")
        cycle_total = brighten_duration + on_duration + darken_duration + off_duration
        if cycle_total == 0.0:
            raise ValueError("At least one pulse phase duration must be non-zero")

        sr = (start_color >> 16) & 0xFF
        sg = (start_color >> 8) & 0xFF
        sb = start_color & 0xFF
        er = (end_color >> 16) & 0xFF
        eg = (end_color >> 8) & 0xFF
        eb = end_color & 0xFF
        palette = PaletteLUT256(bytes([0, sr, sg, sb, 255, er, eg, eb]))

        b_on = brighten_duration
        b_darken = brighten_duration + on_duration
        b_off = brighten_duration + on_duration + darken_duration
        layer = PulseLayer(b_on, b_darken, b_off, cycle_total)

        return Effect(name=name, pixels=PulseEffect(layer, palette, config))


BUILD = PulseBuilder()
