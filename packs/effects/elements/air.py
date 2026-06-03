import random

from effects.effect import Effect, EffectConfig
from effects.layers.add_samples_renderer import AddSamplesRenderer
from effects.layers.layer import Layer
from effects.level import clamp_level, level_lerp
from effects.palette import PaletteLUT256
from effects.shape import Shape
from effects.value import lerp
from engine.effects.manager import EffectBuilder

# fmt: off
_AIR_PALETTE = bytes([
      0,   0,   0,   0,
     68,  54,   0,  98,
    138, 176,  70, 224,
    216, 228, 198, 255,
    255, 255, 255, 255,
])
# fmt: on

_PHASE_IDLE = 0
_PHASE_SWEEP = 1
_PHASE_FADE = 2


class _AirBreeze(Layer):
    """One breeze: IDLE → SWEEP (accelerate + fade-in) → FADE (decelerate + fade-out) → repeat.

    Position scrolls continuously during SWEEP and FADE; the shape is sampled at
    ``(pixel_pos + base_offset + scroll_offset) % 1.0`` scaled by the current
    multiplier.
    """

    __slots__ = [
        "_base_offset",
        "_hide_dur_max",
        "_hide_dur_min",
        "_mult_end_phase",
        "_mult_start",
        "_multiplier",
        "_multiplier_end",
        "_phase",
        "_phase_duration",
        "_phase_elapsed",
        "_scroll_offset",
        "_shape",
        "_speed",
        "_speed_end",
        "_speed_start",
        "_sweep_dur_max",
        "_sweep_dur_min",
    ]

    def __init__(
        self,
        shape,
        multiplier_end: float,
        hide_dur_min: float,
        hide_dur_max: float,
        sweep_dur_min: float,
        sweep_dur_max: float,
        initial_delay: float,
    ) -> None:
        self._shape = shape
        self._multiplier_end = multiplier_end
        self._hide_dur_min = hide_dur_min
        self._hide_dur_max = hide_dur_max
        self._sweep_dur_min = sweep_dur_min
        self._sweep_dur_max = sweep_dur_max

        # Simulation state
        self._base_offset = 0.0
        self._scroll_offset = 0.0
        self._speed = 0.0
        self._speed_start = 0.0
        self._speed_end = 0.0
        self._multiplier = 0.0
        self._mult_start = 0.0
        self._mult_end_phase = 0.0

        # Start in IDLE with a staggered initial delay so multiple breezes don't sync
        self._phase = _PHASE_IDLE
        self._phase_elapsed = 0.0
        self._phase_duration = initial_delay

    def _start_sweep(self) -> None:
        self._phase = _PHASE_SWEEP
        self._phase_elapsed = 0.0
        self._phase_duration = random.uniform(self._sweep_dur_min, self._sweep_dur_max)
        self._base_offset = random.random()
        self._scroll_offset = 0.0
        self._speed_start = 0.3
        self._speed_end = random.uniform(0.75, 1.2)
        self._mult_start = 0.0
        self._mult_end_phase = self._multiplier_end
        self._speed = self._speed_start
        self._multiplier = 0.0

    def _start_fade(self) -> None:
        self._phase = _PHASE_FADE
        self._phase_elapsed = 0.0
        self._phase_duration = random.uniform(0.75, 1.25)
        # Carry current speed and multiplier as start values for the fade
        self._speed_start = self._speed
        self._speed_end = 0.0
        self._mult_start = self._multiplier
        self._mult_end_phase = 0.0

    def _start_idle(self) -> None:
        self._phase = _PHASE_IDLE
        self._phase_elapsed = 0.0
        self._phase_duration = random.uniform(self._hide_dur_min, self._hide_dur_max)

    def update(self, elapsed: float) -> None:
        self._phase_elapsed += elapsed

        if self._phase == _PHASE_IDLE:
            if self._phase_elapsed >= self._phase_duration:
                self._start_sweep()
            return

        # SWEEP or FADE: lerp speed and multiplier by progress
        progress = self._phase_elapsed / self._phase_duration if self._phase_duration > 0.0 else 1.0
        if progress > 1.0:
            progress = 1.0

        self._speed = lerp(self._speed_start, self._speed_end, progress)
        self._multiplier = lerp(self._mult_start, self._mult_end_phase, progress)
        self._scroll_offset = (self._scroll_offset + self._speed * elapsed) % 1.0

        if self._phase_elapsed >= self._phase_duration:
            if self._phase == _PHASE_SWEEP:
                self._start_fade()
            else:
                self._start_idle()

    def sample(self, position: float, pixel_count: int) -> float:
        """Return this breeze's brightness contribution at ``position`` in ``[0.0, 1.0]``."""
        if self._phase == _PHASE_IDLE:
            return 0.0
        pos = (position + self._base_offset + self._scroll_offset) % 1.0
        return self._shape(pos) * self._multiplier


class AirBuilder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Sweeping green-white breezes prototype.

        Each breeze runs its own IDLE/SWEEP/FADE FSM directly on the effect.
        """
        level = clamp_level(int(config.options.get("level", 1)))

        breeze_count = 1 + level // 5
        padding = 0.3 - level_lerp(level, 0.0, 0.3)
        multiplier_end = level_lerp(level, 0.0, 0.5) + 0.50 / breeze_count

        hide_dur_min = 0.5
        hide_dur_max = 3.0 - level_lerp(level, 0.0, 2.0)
        sweep_dur_min = 2.0
        sweep_dur_max = level_lerp(level, 2.5, 5.0)

        shape = Shape.padded(padding, Shape.reverse(Shape.gradient()))

        breezes: list[Layer] = []
        for _ in range(breeze_count):
            breezes.append(
                _AirBreeze(
                    shape,
                    multiplier_end,
                    hide_dur_min,
                    hide_dur_max,
                    sweep_dur_min,
                    sweep_dur_max,
                    initial_delay=random.uniform(0.0, hide_dur_max),
                )
            )

        return Effect(name=name, pixels=AddSamplesRenderer(breezes, PaletteLUT256(_AIR_PALETTE)))


BUILD = AirBuilder()
