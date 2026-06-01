from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from effects.render import EffectConfig
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse_effect import PulseEffect


class WarningStingEffect(PulseEffect):
    """Pixel-rendering pulse effect for RLGL warning phases.

    Combines visual pulse with peak event notification so that
    ``AudioEffectOutput`` can play ``warning_sting_peak.wav`` automatically
    via the verb-based sound lookup on each ``peak`` signal.
    """

    __slots__ = ()


class WarningStingBuilder(EffectBuilder):
    """Builds a :class:`WarningStingEffect` from an :class:`EffectConfig`.

    Reads the same option keys as :class:`~packs.effects.basic.pulse.PulseBuilder`:
    ``start_color``, ``end_color``, ``brighten_duration``, ``on_duration``,
    ``darken_duration``, and ``off_duration``. Level brightness scaling is
    applied to both colors at build time.

    Raises ``ValueError`` if any duration is negative or all durations sum to zero.
    """

    def __call__(self, name: str, config: EffectConfig) -> WarningStingEffect:
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
        sr = int(((start_color_raw >> 16) & 0xFF) * brightness)
        sg = int(((start_color_raw >> 8) & 0xFF) * brightness)
        sb = int((start_color_raw & 0xFF) * brightness)
        er = int(((end_color_raw >> 16) & 0xFF) * brightness)
        eg = int(((end_color_raw >> 8) & 0xFF) * brightness)
        eb = int((end_color_raw & 0xFF) * brightness)
        palette = PaletteLUT256(bytes([0, sr, sg, sb, 255, er, eg, eb]))

        b_on = brighten_duration
        b_darken = brighten_duration + on_duration
        b_off = brighten_duration + on_duration + darken_duration
        layer = PulseLayer(b_on, b_darken, b_off, cycle_total)

        return WarningStingEffect(name, layer, palette, config)


BUILD = WarningStingBuilder()
