from magic.aura import Aura, DamageEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags


class SliceSpell(Spell):
    """Instantly damages the target for a specified amount.

    Level scaling: Increases the damage amount.
    """

    def __init__(self, damage: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.AIR])
        self._base_damage = damage
        self.damage = damage

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        aura.process_event(DamageEvent(self.damage))

        return True

    def on_level_changed(self, level: int) -> None:
        self.damage = Spell.LEVEL_SCALER.scale_value(self._base_damage, level)
