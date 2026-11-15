"""Tag scene "hit" effect — shared, unmistakable hit moment on ``Scope.Global.MAIN``.

Built on ``basic.pulse`` for pixels: a quick white flash. Layers on a one-shot
``scene.hit_start`` audio clip with ``stops_effect=True`` so the effect ends —
and the scope returns to dark — the moment the clip finishes, plus a
strong-buzz/pause/strong-click haptic sequence for a punchier hit feel.
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
