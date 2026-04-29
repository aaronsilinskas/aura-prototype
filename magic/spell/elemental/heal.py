from magic.aura import Aura, HealEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags


class HealSpell(Spell):
    """Instantly heals the target for a specified amount.
    
    Level scaling: Increases the healing amount.
    """

    def __init__(self, healing: float) -> None:
        super().__init__([SpellTags.BUFF, ElementTags.LIGHT])
        self._base_healing = healing
        self.healing = healing

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        aura.process_event(HealEvent(self.healing))

        return True  # Remove after one application

    def _update_level(self, level: int) -> None:
        self.healing = Spell.LEVEL_SCALER.scale_value(self._base_healing, level)
