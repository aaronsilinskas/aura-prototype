from effects.effect import Effect, EffectConfig


class EffectBuilder:
    """Factory interface for constructing ``Effect`` instances by name.

    Concrete implementations look up the named effect and return an effect
    configured for the given ``EffectConfig``. Raise ``KeyError`` or
    ``ValueError`` for unregistered names.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Build an Effect for the named effect.

        Args:
            name: The registered effect name (e.g. ``"color.flash"``).
            config: Runtime configuration for the render pass. ``config.get_option``
                carries any effect-specific parameters (e.g. duration, color).
                ``config.resolution`` describes the output hardware.

        Returns:
            A configured ``Effect`` ready to be advanced each frame.
        """
        raise NotImplementedError
