from magic.aura import Aura, AuraEvent, HealEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class ChargeSpell(Spell):
    """Increase the effectiveness of healing spells for a duration.

    Level scaling: Increases the healing multiplier.
    """

    def __init__(self, healing_multiplier: float, duration: float) -> None:
        super().__init__([SpellTags.BUFF, ElementTags.LIGHTNING])
        self.duration = Duration(duration)
        self._base_healing_multiplier = healing_multiplier
        self.healing_multiplier = healing_multiplier

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if isinstance(event, HealEvent):
            event.amount *= self.healing_multiplier

    def on_level_changed(self, level: int) -> None:
        self.healing_multiplier = Spell.LEVEL_SCALER.scale_value(
            self._base_healing_multiplier, level
        )
