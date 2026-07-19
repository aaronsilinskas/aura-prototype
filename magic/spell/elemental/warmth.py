from magic.aura import Aura, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags


class WarmthSpell(Spell):
    """Remove debuffs from the water and ice elements.

    Level scaling: No scaling (instant removal effect).
    """

    def __init__(self) -> None:
        super().__init__([SpellTags.BUFF, ElementTags.FIRE])

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        water_debuffs = aura.spells.get_by_tag(ElementTags.WATER, SpellTags.DEBUFF)
        ice_debuffs = aura.spells.get_by_tag(ElementTags.ICE, SpellTags.DEBUFF)

        for spell in water_debuffs + ice_debuffs:
            aura.remove_spell(spell)

        return True

    def on_level_changed(self, level: int) -> None:
        pass
