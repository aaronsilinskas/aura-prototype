from magic.aura import Aura
from magic.spell.combo.combo import SpellCombination
from magic.spell.elemental.ignite import IgniteSpell


class CombustCombination(SpellCombination):
    """Combines multiple Ignite spells into a single more powerful Ignite.

    When two or more Ignite spells are present on the Aura, this combination
    removes all of them and creates a new Ignite spell with:
    - Total damage per second: Sum of all individual Ignite damage values
    - Duration: Maximum duration among all Ignite spells
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
