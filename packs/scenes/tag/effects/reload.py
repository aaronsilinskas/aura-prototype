"""Tag scene "reload" effect — self-animating hold-to-reload fill on ``GLOBAL.BUFF``.

Built on :class:`ProgressFillEffect` (the self-animating fill component): a
0->1 fill over the ``duration`` option, paired with a looping reload
sound. Issued with ``set_effect`` once at the start of a reload — the fill
animates on its own clock, so no per-tick re-issue is needed and the audio
loop stays intact.
"""

from __future__ import annotations

from effects.effect import AudioPlaybackConfig, Effect, EffectAudio, EffectConfig
from effects.layers.progress_layer import ProgressLayer
from engine.effects.manager import EffectBuilder
from packs.scenes.tag.effects.helpers.progress_fill_effect import ProgressFillEffect

_RELOAD_AUDIO = EffectAudio(clips={"start": AudioPlaybackConfig(name="scene.reload", loop=True)})

_DEFAULT_COLOR = 0xFF0000
_DEFAULT_DURATION = 3.0


class _Builder(EffectBuilder):
    def __call__(self, name: str, config: EffectConfig) -> Effect:
        color = config.get_option("color", _DEFAULT_COLOR)
        duration = config.get_option("duration", _DEFAULT_DURATION)
        layer = ProgressLayer(0.0)
        pixels = ProgressFillEffect(layer, color=color, duration=duration)
        return Effect(name=name, pixels=pixels, audio=_RELOAD_AUDIO)


BUILD = _Builder()
