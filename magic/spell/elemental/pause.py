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
        super().__init__(tags=[SpellTags.DEBUFF, ElementTags.TIME])
        self._base_duration = duration
        self.duration = Duration(duration)
        self._modifier = ValueModifier(multiplier=duration, duration=duration)

    def start(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.add(self._modifier)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def stop(self, aura: Aura) -> None:
        aura.cast_delay.modifiers.remove(self._modifier)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        """Cancels casts while paused; the first pause cast passes and also pauses this Aura."""
        if not isinstance(event, CastEvent):
            return

        event_spell = event.spell
        if isinstance(event_spell, PauseSpell):
            already_paused = aura.spells.get_by_class(PauseSpell) != []
            if not already_paused:
                aura.add_spell(PauseSpell(self.duration.length))

            # Cancel a stacking pause; let the first pause through to pause this Aura.
            event.is_canceled = already_paused
        else:
            event.is_canceled = True

    def on_level_changed(self, level: int) -> None:
        new_length = Spell.LEVEL_SCALER.scale_value(self._base_duration, level)
        self.duration.length = new_length
