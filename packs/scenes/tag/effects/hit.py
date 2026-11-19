"""Tag scene "hit" effect — shared, unmistakable hit moment on ``Scope.Global.MAIN``.

The clip's ``stops_effect=True`` ends the effect, returning the scope to dark,
the moment the clip finishes.
"""

from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder
from packs.effects.basic.pulse import PulseBuilder

BUILD = ComposedEffectBuilder(
    PulseBuilder(),
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(
                name="scene.hit_start", loop=False, stops_effect=True
            )
        }
    ),
    haptic=EffectHaptic(
        patterns={
            EffectVerb.START: HapticPattern(
                [
                    HapticPattern.STRONG_BUZZ,
                    HapticPattern.PAUSE_250,
                    HapticPattern.STRONG_CLICK,
                ]
            )
        }
    ),
)
