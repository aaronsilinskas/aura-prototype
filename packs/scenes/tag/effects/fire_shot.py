"""Tag scene "fire_shot" effect — one-shot felt feedback for a Button-A shot.

The clip's ``stops_effect=True`` ends the whole effect, pixels and haptic
included, when the clip finishes, returning ``Scope.DIRECTIONAL`` to dark.
"""

from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder
from packs.effects.basic.solid import SolidBuilder

BUILD = ComposedEffectBuilder(
    SolidBuilder(),
    options={"color": 0xFFFFFF},
    audio=EffectAudio(
        clips={
            EffectVerb.START: AudioPlaybackConfig(
                name="scene.fire_shot_start", loop=False, stops_effect=True
            )
        }
    ),
    haptic=EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.STRONG_CLICK])}),
)
