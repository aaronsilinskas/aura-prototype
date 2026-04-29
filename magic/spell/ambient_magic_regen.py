from magic.aura import Aura, HealEvent, Spell, SpellTags


class AmbientMagicRegenSpell(Spell):
    """Provides continuous ambient magic regeneration per second.
    
    Level scaling: Increases the regeneration amount per second.
    """
    
    def __init__(self, amount_per_second: float) -> None:
        super().__init__([SpellTags.BUFF])
        self._base_amount_per_second: float = amount_per_second
        self.amount_per_second: float = amount_per_second

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        heal_amount = self.amount_per_second * elapsed_time
        aura.process_event(HealEvent(heal_amount))

        return False  # Don't remove this spell

    def _update_level(self, level: int) -> None:
        self.amount_per_second = Spell.LEVEL_SCALER.scale_value(
            self._base_amount_per_second, level
        )
