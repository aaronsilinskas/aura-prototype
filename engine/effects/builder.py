from __future__ import annotations

from effects.effect import Effect, EffectAudio, EffectConfig, EffectHaptic


class EffectBuilder:
    """Factory interface for constructing ``Effect`` instances by name."""

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Build an Effect for the named effect.

        Args:
            name: The bare effect name, without its pack or ``scene`` prefix
                (e.g. ``"flash"`` for ``"color.flash"``).
            config: Runtime configuration for the render pass. ``config.get_option``
                carries any effect-specific parameters (e.g. duration, color).
                ``config.resolution`` describes the output hardware.

        Returns:
            A configured ``Effect`` ready to be advanced each frame, new on
            every call, so callers such as ``ComposedEffectBuilder`` may modify it.
        """
        raise NotImplementedError


class ComposedEffectBuilder(EffectBuilder):
    """Builds a base effect's pixels plus a declared ``EffectAudio`` and ``EffectHaptic``.

    *options* fix those keys of the base's options; every other caller option,
    and the caller's listeners, pass through. The base's pixels carry their
    declared custom verbs, so clips and patterns may be keyed on them (a
    pulse's ``PEAK``), and ``EffectManager`` checks those keys as for any
    effect. Without a base the effect has no pixels. Whatever audio or haptic
    the base built is replaced.

    Raises:
        ValueError: *options* are given without a *base* to apply them to.
    """

    def __init__(
        self,
        base: EffectBuilder | None = None,
        options: dict[str, object] | None = None,
        audio: EffectAudio | None = None,
        haptic: EffectHaptic | None = None,
    ) -> None:
        if base is None and options is not None:
            raise ValueError("ComposedEffectBuilder options need a base to apply them to")
        self._base = base
        self._options = options
        self._audio = audio
        self._haptic = haptic

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        base = self._base
        if base is None:
            return Effect(name, audio=self._audio, haptic=self._haptic)
        options = self._options
        if options is not None:
            config = config.with_options(options)
        effect = base(name, config)
        effect.audio = self._audio
        effect.haptic = self._haptic
        return effect
