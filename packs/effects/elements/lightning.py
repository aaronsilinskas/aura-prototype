import random

from effects.effect import Effect, EffectConfig, EffectPixels, PixelBuffer
from effects.layers.layer import Layer
from effects.level import clamp_level
from effects.palette import Palette, PaletteLUT256
from effects.shape import EffectShapeFunc, Shape
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
        "at_strike",
    ]

    def __init__(
        self,
        shape: EffectShapeFunc,
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
        self.at_strike = False

    def update(self, elapsed: float) -> None:
        self._phase_elapsed += elapsed
        if self._phase_elapsed < self._phase_duration:
            self.at_strike = False
            return

        # Phase transition
        transitioning_from_idle = self._phase == _PHASE_IDLE
        if transitioning_from_idle:
            self._bolt_offset = random.random()
            self._start_brightness = random.uniform(0.25, 1.0)
            self._phase_duration = random.uniform(
                self._strike_duration_min, self._strike_duration_max
            )
        else:
            self._phase_duration = random.uniform(0.1, self._hide_max)

        self._phase = _PHASE_STRIKE if self._phase == _PHASE_IDLE else _PHASE_IDLE
        self._phase_elapsed = 0.0
        self.at_strike = transitioning_from_idle

    def sample(self, position: float, pixel_count: int) -> float:
        """Return the bolt's brightness contribution at ``position`` in ``[0.0, 1.0]``."""
        if self._phase == _PHASE_IDLE:
            return 0.0
        progress = self._phase_elapsed / self._phase_duration if self._phase_duration > 0.0 else 1.0
        brightness = self._start_brightness * (1.0 - progress)
        return self._shape((position + self._bolt_offset) % 1.0) * brightness


class LightningEffect(EffectPixels):
    """Renders multiple lightning bolts and fires a 'strike' event on IDLE→STRIKE transitions."""

    __slots__ = ["_bolts", "_config", "_palette"]

    def __init__(
        self,
        bolts: list[_LightningBolt],
        palette: Palette,
        config: EffectConfig,
    ) -> None:
        self._bolts = bolts
        self._palette = palette
        self._config = config

    def update(self, elapsed: float) -> None:
        """Advance all bolts; call notify_listeners('strike') if any bolt just struck."""
        for bolt in self._bolts:
            bolt.update(elapsed)
        struck = False
        for bolt in self._bolts:
            if bolt.at_strike:
                struck = True
                break
        if struck:
            self._config.notify_listeners("strike")

    def render(self, output: PixelBuffer) -> None:
        """Sum bolt samples per pixel, clamp to 1.0, and write palette-mapped colors."""
        count = len(output)
        inv_count = 1.0 / count
        palette = self._palette
        bolts = self._bolts
        for i in range(count):
            pos = i * inv_count
            total = 0.0
            for bolt in bolts:
                total += bolt.sample(pos, count)
            if total > 1.0:
                total = 1.0
            output[i] = palette.lookup(total)


class LightningBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Blinding orange flashes at random positions, prototype version.

        runs its own IDLE/STRIKE FSM directly on the effect.
        """
        level = clamp_level(int(config.options.get("level", 1)))

        hide_max = 1.5 - (1 - 1 / level)
        strike_duration_max = 1.25 - (1 - 1 / level)
        strike_duration_min = 0.5
        branch_count = max(1, level // 2)

        shape = Shape.padded(0.25, Shape.centered_gradient())

        bolts = [
            _LightningBolt(shape, hide_max, strike_duration_min, strike_duration_max)
            for _ in range(branch_count)
        ]

        return Effect(
            name=name,
            pixels=LightningEffect(bolts, PaletteLUT256(_LIGHTNING_PALETTE), config),
        )


BUILD = LightningBuilder()
