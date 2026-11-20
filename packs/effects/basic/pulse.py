from effects.effect import Effect, EffectConfig
from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from engine.effects.builder import EffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect


class PulseBuilder(EffectBuilder):
    """Builds a :class:`PulseEffect` from color and phase-duration options.

    Raises ``ValueError``, from :class:`PulseLayer`, if any duration is
    negative or if all durations are zero.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        start_color = config.get_option("start_color", 0x000000)
        end_color = config.get_option("end_color", 0xFFFFFF)
        brighten_duration = config.get_option("brighten_duration", 0.5)
        on_duration = config.get_option("on_duration", 0.5)
        darken_duration = config.get_option("darken_duration", 0.5)
        off_duration = config.get_option("off_duration", 0.5)

        sr = (start_color >> 16) & 0xFF
        sg = (start_color >> 8) & 0xFF
        sb = start_color & 0xFF
        er = (end_color >> 16) & 0xFF
        eg = (end_color >> 8) & 0xFF
        eb = end_color & 0xFF
        palette = PaletteLUT256(bytes([0, sr, sg, sb, 255, er, eg, eb]))

        layer = PulseLayer(brighten_duration, on_duration, darken_duration, off_duration)

        return Effect(name=name, pixels=PulseEffect(layer, palette, config))


BUILD = PulseBuilder()
