from __future__ import annotations

from effects.effect import EffectConfig, EffectVerb
from effects.layers.pulse_layer import PulseLayer
from effects.layers.renderer import LayerRenderer
from effects.palette import Palette

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Final


class PulseEffect(LayerRenderer):
    """Renders a :class:`PulseLayer` through a palette, emitting ``PEAK`` each time it peaks."""

    PEAK: Final = EffectVerb("peak")
    VERBS: tuple[EffectVerb, ...] = (PEAK,)

    __slots__ = ("_config", "_pulse")

    def __init__(
        self,
        layer: PulseLayer,
        palette: Palette,
        config: EffectConfig,
    ) -> None:
        super().__init__(layer, palette)
        self._pulse = layer
        self._config = config

    def update(self, elapsed: float) -> None:
        super().update(elapsed)
        if self._pulse.at_peak:
            self._config.notify_listeners(self.PEAK)
