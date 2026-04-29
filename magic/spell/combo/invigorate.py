from magic.aura import Aura
from magic.spell.combo.combo import SpellCombination
from magic.spell.elemental.regen import RegenSpell
from magic.values import ValueModifier


class InvigorateCombination(SpellCombination):
    """When three or more Regen spells are present on the Aura, this combination
    increases the max magic of the Aura. The max magic stays increased for a
    duration after the Regen spell count drops below three.
    """

    def __init__(self, max_magic_multiplier: float, duration: float) -> None:
        super().__init__()
        self._max_magic_multiplier = max_magic_multiplier
        self._max_magic_modifier = ValueModifier(max_magic_multiplier, duration)

    def check(self, aura: Aura) -> bool:
        regen_spells = aura.spells.get_by_class(RegenSpell)
        if len(regen_spells) >= 3:
            self._max_magic_modifier.duration.reset()
            if aura.magic.max.modifiers.add(self._max_magic_modifier):
                return True

        return False
