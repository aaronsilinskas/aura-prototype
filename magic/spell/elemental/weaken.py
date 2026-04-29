from magic.aura import Aura, AuraEvent, CastEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class WeakenSpell(Spell):
    """Reduces the level of spells cast by the target for a duration.

    Level scaling: Increases the level reduction.
    """

    def __init__(self, reduction: float, duration: float) -> None:
        super().__init__(tags=[SpellTags.DEBUFF, ElementTags.WATER])
        self._base_reduction = max(0, min(reduction, 1))
        self.reduction = self._base_reduction
        self.duration = Duration(duration)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if isinstance(event, CastEvent):
            spell = event.spell
            spell.level = int(spell.level * (1 - self.reduction))

    def _update_level(self, level: int) -> None:
        self.reduction = Spell.LEVEL_SCALER.scale_percentage(
            self._base_reduction, level
        )
