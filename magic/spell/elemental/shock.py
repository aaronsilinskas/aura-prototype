from magic.aura import Aura, AuraEvent, HealEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class ShockSpell(Spell):
    """Reduces healing by a percentage for a duration.
    
    Level scaling: Increases the heal reduction percentage.
    """

    def __init__(self, heal_reduction_percentage: float, duration: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.LIGHTNING])
        self.duration = Duration(duration)
        self._base_heal_reduction_percentage = max(
            min(heal_reduction_percentage, 1.0), 0.0
        )
        self.heal_reduction_percentage = self._base_heal_reduction_percentage

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if isinstance(event, HealEvent):
            event.amount *= 1 - self.heal_reduction_percentage

    def _update_level(self, level: int) -> None:
        self.heal_reduction_percentage = Spell.LEVEL_SCALER.scale_value(
            self._base_heal_reduction_percentage, level
        )
