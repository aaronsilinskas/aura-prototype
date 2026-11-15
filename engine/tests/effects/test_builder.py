from effects.effect import (
    AudioPlaybackConfig,
    EffectAudio,
    EffectConfig,
    EffectHaptic,
    EffectVerb,
    HapticPattern,
)
from engine.effects.builder import ComposedEffectBuilder
from engine.tests.effects.helpers import CapturingEffectBuilder, SpyEffectBuilder
from packs.effects.basic.helpers.pulse_effect import PulseEffect
from packs.effects.basic.pulse import PulseBuilder

_AUDIO = EffectAudio(clips={EffectVerb.START: AudioPlaybackConfig(name="sfx.boom", loop=False)})
_HAPTIC = EffectHaptic(patterns={EffectVerb.START: HapticPattern([HapticPattern.STRONG_CLICK])})


def test_without_a_base_the_effect_has_no_pixels_and_the_declared_audio_and_haptic() -> None:
    build = ComposedEffectBuilder(audio=_AUDIO, haptic=_HAPTIC)

    effect = build("scene.cue", EffectConfig(resolution=10))

    assert effect.name == "scene.cue"
    assert effect.pixels is None
    assert effect.audio is _AUDIO
    assert effect.haptic is _HAPTIC


def test_with_a_base_the_effect_carries_the_base_pixels_and_the_declared_audio_and_haptic() -> None:
    base = SpyEffectBuilder()
    build = ComposedEffectBuilder(base, audio=_AUDIO, haptic=_HAPTIC)

    effect = build("scene.hit", EffectConfig(resolution=10))

    assert effect.name == "scene.hit"
    assert base.created == [effect.pixels]
    assert effect.audio is _AUDIO
    assert effect.haptic is _HAPTIC


def test_with_a_base_and_nothing_added_the_effect_has_no_audio_or_haptic() -> None:
    build = ComposedEffectBuilder(SpyEffectBuilder())

    effect = build("scene.glow", EffectConfig(resolution=10))

    assert effect.pixels is not None
    assert effect.audio is None
    assert effect.haptic is None


def test_caller_options_pass_through_to_the_base() -> None:
    base = CapturingEffectBuilder()
    build = ComposedEffectBuilder(base)

    build("scene.hit", EffectConfig(resolution=7, options={"color": 0x00FF00}))

    assert base.last_config is not None
    assert base.last_config.resolution == 7
    assert base.last_config.get_option("color", 0) == 0x00FF00


def test_fixed_options_override_the_caller_options_and_the_rest_pass_through() -> None:
    base = CapturingEffectBuilder()
    build = ComposedEffectBuilder(base, options={"color": 0xFFFFFF})

    build("scene.flash", EffectConfig(resolution=7, options={"color": 0x00FF00, "level": 3}))

    assert base.last_config is not None
    assert base.last_config.get_option("color", 0) == 0xFFFFFF
    assert base.last_config.get_option("level", 0) == 3
    assert base.last_config.resolution == 7


def test_fixed_options_leave_the_caller_listeners_on_the_base_config() -> None:
    heard: list[EffectVerb] = []
    base = CapturingEffectBuilder()
    build = ComposedEffectBuilder(base, options={"color": 0xFFFFFF})

    build("scene.flash", EffectConfig(resolution=7, listeners=[heard.append]))
    assert base.last_config is not None
    base.last_config.notify_listeners(EffectVerb.START)

    assert heard == [EffectVerb.START]


def test_fixed_options_leave_the_caller_config_unchanged() -> None:
    build = ComposedEffectBuilder(CapturingEffectBuilder(), options={"color": 0xFFFFFF})
    caller = EffectConfig(resolution=7, options={"color": 0x00FF00})

    build("scene.flash", caller)

    assert caller.get_option("color", 0) == 0x00FF00


def test_the_effect_emits_the_custom_verbs_its_base_pixels_declare() -> None:
    build = ComposedEffectBuilder(PulseBuilder(), audio=_AUDIO)

    effect = build("scene.warn", EffectConfig(resolution=10))

    assert PulseEffect.PEAK in effect.emitted_verbs()
