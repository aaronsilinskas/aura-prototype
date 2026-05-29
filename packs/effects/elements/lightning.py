import random

from effects.layers.add_samples_renderer import AddSamplesRenderer
from effects.layers.layer import Layer
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.shape import Shape
from engine.effects.manager import EffectBuilder

# fmt: off
_LIGHTNING_PALETTE = bytes([  0,   0,   0,   0,
                             255, 255, 100,   0])
# fmt: on

_PHASE_IDLE = 0
_PHASE_STRIKE = 1


class _LightningBolt(Layer):
    """One independent bolt: alternates between idle (dark) and strike (flash+fade).

    All values are resolved at construction / on each IDLE→STRIKE transition,
    so this class has no dependency on DynamicValue or VG.
    """

    __slots__ = [
        "_bolt_offset",
        "_hide_max",
        "_phase",
        "_phase_duration",
        "_phase_elapsed",
        "_shape",
        "_start_brightness",
        "_strike_duration_max",
        "_strike_duration_min",
    ]

    def __init__(
        self,
        shape,
        hide_max: float,
        strike_duration_min: float,
        strike_duration_max: float,
    ) -> None:
        self._shape = shape
        self._hide_max = hide_max
        self._strike_duration_min = strike_duration_min
        self._strike_duration_max = strike_duration_max
        self._bolt_offset = 0.0
        self._start_brightness = 1.0
        self._phase = _PHASE_IDLE
        self._phase_elapsed = 0.0
        self._phase_duration = random.uniform(0.1, hide_max)

    def update(self, elapsed: float) -> None:
        self._phase_elapsed += elapsed
        if self._phase_elapsed < self._phase_duration:
            return

        # Phase transition
        if self._phase == _PHASE_IDLE:
            self._bolt_offset = random.random()
            self._start_brightness = random.uniform(0.25, 1.0)
            self._phase_duration = random.uniform(
                self._strike_duration_min, self._strike_duration_max
            )
        else:
            self._phase_duration = random.uniform(0.1, self._hide_max)

        self._phase = _PHASE_STRIKE if self._phase == _PHASE_IDLE else _PHASE_IDLE
        self._phase_elapsed = 0.0

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the bolt's brightness contribution at ``position`` in ``[0.0, 1.0]``."""
        if self._phase == _PHASE_IDLE:
            return 0.0
        progress = self._phase_elapsed / self._phase_duration if self._phase_duration > 0.0 else 1.0
        brightness = self._start_brightness * (1.0 - progress)
        return self._shape((position + self._bolt_offset) % 1.0) * brightness


class LightningPrototypeBuilder(EffectBuilder):
    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Blinding orange flashes at random positions, prototype version.

        Bypasses Effect/EffectStep/EffectState machinery entirely — each bolt
        runs its own IDLE/STRIKE FSM directly on the renderer.
        """
        level = config.level

        hide_max = 1.5 - (1 - 1 / level)
        strike_duration_max = 1.25 - (1 - 1 / level)
        strike_duration_min = 0.5
        branch_count = max(1, level // 2)

        shape = Shape.padded(0.25, Shape.centered_gradient())

        bolts = [
            _LightningBolt(shape, hide_max, strike_duration_min, strike_duration_max)
            for _ in range(branch_count)
        ]

        return AddSamplesRenderer(name, bolts, PaletteLUT256(_LIGHTNING_PALETTE))


BUILD = LightningPrototypeBuilder()
