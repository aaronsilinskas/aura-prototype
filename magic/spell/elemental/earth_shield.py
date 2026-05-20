from magic.aura import Aura, AuraEvent, DamageEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Counter, Duration


class EarthShieldSpell(Spell):
    """Resists incoming damage for a number of hits or duration.

    Level scaling: Increases the damage reduction percentage up to 100%.
    """

    def __init__(self, reduction: float, max_hits: int, duration: float) -> None:
        super().__init__([SpellTags.BUFF, SpellTags.SHIELD, ElementTags.EARTH])
        self.duration = Duration(duration)
        self._base_reduction = max(0, min(reduction, 1))
        self.reduction = self._base_reduction
        self.hits = Counter(max=max_hits)

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        if self.duration.update(elapsed_time):
            return True

        return self.hits.is_max

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        if self.duration.is_expired or self.hits.is_max:
            return

        if isinstance(event, DamageEvent):
            event.amount *= 1 - self.reduction
            self.hits.increment()

    def _update_level(self, level: int) -> None:
        self.reduction = Spell.LEVEL_SCALER.scale_percentage(self._base_reduction, level)
