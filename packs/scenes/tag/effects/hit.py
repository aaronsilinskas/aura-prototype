"""Tag scene "hit" effect — shared, unmistakable hit moment on ``Scope.Global.MAIN``.

Built on ``basic.pulse`` for pixels: a quick red flash. Layers on a one-shot
``start`` audio clip (the ``game_over_sting`` composition pattern) with
``stops_effect=True`` so the effect ends — and the scope returns to dark —
the moment the clip finishes, plus a strong-buzz/pause/strong-click
haptic sequence for a punchier hit feel.
"""

from __future__ import annotations

from effects.effect import (
    AudioPlaybackConfig,
    Effect,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    HapticPattern,
)
from engine.effects.manager import EffectBuilder
from packs.effects.basic.pulse import PulseBuilder

_pulse = PulseBuilder()

_HIT_HAPTIC = EffectHaptic(
    patterns={
        "start": HapticPattern(
            [
                HapticPattern.STRONG_BUZZ,
                HapticPattern.PAUSE_250,
                HapticPattern.STRONG_CLICK,
            ]
        )
    }
)


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
            haptic=_HIT_HAPTIC,
        )


BUILD = _Builder()
