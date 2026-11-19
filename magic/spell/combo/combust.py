from magic.aura import Aura
from magic.spell.combo.combo import SpellCombination
from magic.spell.elemental.ignite import IgniteSpell


class CombustCombination(SpellCombination):
    """Merges two or more Ignite spells into one with their summed damage per second
    and the longest duration.
    """

    def check(self, aura: Aura) -> bool:
        ignite_spells = aura.spells.get_by_class(IgniteSpell)
        if len(ignite_spells) >= 2:
            total_damage_per_second: float = 0.0
            max_duration: float = 0.0
            for ignite in ignite_spells:
                total_damage_per_second += ignite.damage_per_second
                max_duration = max(max_duration, ignite.duration.length)
                aura.remove_spell(ignite)

            combined_ignite = IgniteSpell(
                damage_per_second=total_damage_per_second, duration=max_duration
            )
            aura.add_spell(combined_ignite)
            return True

        return False
