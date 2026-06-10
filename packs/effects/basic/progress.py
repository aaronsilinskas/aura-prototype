from effects.effect import Effect, EffectConfig
from effects.layers.progress_layer import ProgressLayer
from engine.effects.manager import EffectBuilder
from packs.effects.basic.helpers.progress_effect import ProgressEffect


class ProgressBuilder(EffectBuilder):
    """Builds a :class:`ProgressEffect` wrapping a :class:`ProgressLayer`.

    Reads ``color`` (default ``0xFFFFFF``, stored raw/unscaled) and ``progress``
    (default ``0.0``, clamped to ``[0.0, 1.0]`` by the layer) from options.
    The ``brightness`` option is silently ignored; brightness is an
    output-level concern applied by ``MatrixEffectOutput`` at render time.

    No ``Palette``/``PaletteLUT256`` is allocated, so re-issuing ``set_effect``
    every tick is cheap.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        color = config.get_option("color", 0xFFFFFF)
        progress = config.get_option("progress", 0.0)
        layer = ProgressLayer(progress)
        return Effect(name=name, pixels=ProgressEffect(layer, color))


BUILD = ProgressBuilder()
