from magic.aura import Aura, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration


class FlashSpell(Spell):
    """A spell that temporarily turns all visual indicators white until the duration expires. Visual
    effects must listen for this spell and implement the effect.
    
    Level scaling: Increases the duration.
    """

    def __init__(self, duration: float) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.LIGHT])
        self._base_duration = duration
        self.duration = Duration(duration)  # in seconds

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        return self.duration.update(elapsed_time)

    def _update_level(self, level: int) -> None:
        self.duration.length = Spell.LEVEL_SCALER.scale_value(
            self._base_duration, level
        )
