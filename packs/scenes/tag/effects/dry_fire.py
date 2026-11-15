"""Tag scene "dry_fire" effect — audio + haptic sting for an empty-magazine trigger pull.

No pixel output — issued with ``add_effect`` on
``Scope.DIRECTIONAL`` so it layers alongside the ``Global.BUFF`` reload it
accompanies without a pixel conflict. One-shot with ``stops_effect=True`` so
the effect (and its haptic) ends when the clip finishes. Deliberately
lighter than ``scene.fire_shot`` — a soft bump rather than a double click —
since no shot was actually fired.
"""

from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder

BUILD = ComposedEffectBuilder(
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(
                name="scene.dry_fire_start", loop=False, stops_effect=True
            ),
        }
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.SOFT_BUMP])}),
)
