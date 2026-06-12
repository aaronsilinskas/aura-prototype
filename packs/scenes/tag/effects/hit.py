"""Tag scene "hit" effect — shared, unmistakable hit moment on ``Scope.Global.MAIN``.

Built on ``basic.pulse`` for pixels: a quick red flash. Layers on a one-shot
``start`` audio clip (the ``game_over_sting`` composition pattern) with
``stops_effect=True`` so the effect ends — and the scope returns to dark —
the moment the clip finishes, plus a single strong-buzz vibration pulse.
"""

from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectVibration,
    VibrationConfig,
)
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_HIT_VIBRATION = EffectVibration(patterns={"start": VibrationConfig([VibrationConfig.STRONG_BUZZ])})


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = _pulse(name, config)
        return Effect(
            name=base.name,
            pixels=base.pixels,
            audio=EffectAudio(
                clips={
                    "start": AudioPlaybackConfig(
                        name=name + "_start", loop=False, stops_effect=True
                    )
                }
            ),
            vibration=_HIT_VIBRATION,
        )


BUILD = _Builder()
