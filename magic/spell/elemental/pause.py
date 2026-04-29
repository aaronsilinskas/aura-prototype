from magic.aura import Aura, AuraEvent, CastEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration, ValueModifier


class PauseSpell(Spell):
    """Prevents spell casting for a duration and multiplies cast delay.
    Note: When this spell is cast, it pauses both the caster and the
    target Auras.

    While active:
    - Cancels all spell casts
    - Multiplies cast delay by the pause duration
    - Does not affect damage, healing, or spell hits
    
    Level scaling: Increases the pause duration.
    """

    def __init__(self, duration: float) -> None:
        """Initialize a PauseSpell.

        Args:
            duration: How long the pause lasts and the cast delay multiplier.
        """
        super().__init__(tags=[SpellTags.DEBUFF, ElementTags.TIME])
        self._base_duration = duration
        self.duration = Duration(duration)
        self._modifier = ValueModifier(multiplier=duration, duration=duration)

    def start(self, aura: Aura) -> None:
        """Apply the cast delay modifier.

        Args:
            aura: The aura being affected.
        """
        aura.cast_delay.modifiers.add(self._modifier)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        """Updates the pause duration.

        Args:
            aura: The aura being affected.
            elapsed_time: The time passed since the last update.

        Returns:
            True if the pause has expired, False otherwise.
        """
        return self.duration.update(elapsed_time)

    def stop(self, aura: Aura) -> None:
        """Remove the cast delay modifier.

        Args:
            aura: The aura being released.
        """
        aura.cast_delay.modifiers.remove(self._modifier)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        """Cancel spell casts while paused. If not yet paused,
        allow the first pause cast to pass but also pause this Aura

        Args:
            aura: The aura processing the event.
            event: The event to potentially cancel.
        """
        if not isinstance(event, CastEvent):
            return

        event_spell = event.spell
        if isinstance(event_spell, PauseSpell):
            # Check if a pause is already active
            already_paused = aura.spells.get_by_class(PauseSpell) != []
            if not already_paused:
                # No pause active, add a new one with the same duration as this spell
                aura.add_spell(PauseSpell(self.duration.length))

            # Cancel the cast if already paused (prevent stacking)
            # Allow the cast if not already paused (first pause)
            event.is_canceled = already_paused
        else:
            # Cancel all non-pause spell casts while paused
            event.is_canceled = True

    def _update_level(self, level: int) -> None:
        new_length = Spell.LEVEL_SCALER.scale_value(self._base_duration, level)
        self.duration.length = new_length
