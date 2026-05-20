from magic.aura import Aura, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class RegenSpell(Spell):
    """A spell that provides magic regeneration over time.

    Level scaling: Increases the regeneration rate per second.
    """

    def __init__(self, regen_rate: float, duration: float):
        """Initialize a RegenSpell.

        Args:
            regen_rate: The rate of magic regeneration per second.
            duration: The duration of the spell in seconds.
        """
        super().__init__(tags=[SpellTags.BUFF, ElementTags.WATER])
        self._base_regen_rate = regen_rate
        self.regen_rate = regen_rate
        self.duration = Duration(duration)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        regen_amount = self.regen_rate * min(elapsed_time, self.duration.remaining)
        aura.magic.value += regen_amount

        return self.duration.update(elapsed_time)

    def on_level_changed(self, level: int) -> None:
        self.regen_rate = Spell.LEVEL_SCALER.scale_value(self._base_regen_rate, level)
