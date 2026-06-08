from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectPixels,
    PixelBuffer,
)
from effects.layers.pulse_layer import PulseLayer
from effects.palette import PaletteLUT256
from engine.effects.manager import EffectBuilder

_RED_PALETTE = PaletteLUT256(bytes([0, 0, 0, 0, 255, 255, 0, 0]))
_GREEN_PALETTE = PaletteLUT256(bytes([0, 0, 0, 0, 255, 0, 255, 0]))

_BRIGHTEN = 0.3
_ON = 0.2
_DARKEN = 0.3
_OFF = 0.2
_CYCLE_TOTAL = _BRIGHTEN + _ON + _DARKEN + _OFF
_INV_CYCLE_TOTAL = 1.0 / _CYCLE_TOTAL


class _ReadyPixels(EffectPixels):
    __slots__ = ("_color", "_elapsed", "_layer")

    def __init__(self, layer: PulseLayer) -> None:
        self._layer = layer
        self._elapsed = 0.0
        self._color = 0

    def update(self, elapsed: float) -> None:
        self._layer.update(elapsed)
        self._elapsed += elapsed
        red_cycle = int(self._elapsed * _INV_CYCLE_TOTAL) % 2 == 0
        palette = _RED_PALETTE if red_cycle else _GREEN_PALETTE
        self._color = palette.lookup(self._layer.sample(0.0, 0))

    def render(self, output: PixelBuffer) -> None:
        color = self._color
        for i in range(len(output)):
            output[i] = color


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        layer = PulseLayer(
            _BRIGHTEN,
            _BRIGHTEN + _ON,
            _BRIGHTEN + _ON + _DARKEN,
            _CYCLE_TOTAL,
        )
        return Effect(
            name=name,
            pixels=_ReadyPixels(layer),
            audio=EffectAudio(
                clips={"start": AudioPlaybackConfig(name=name + "_start", loop=False)}
            ),
        )


BUILD = _Builder()
