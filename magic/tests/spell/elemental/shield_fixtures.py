import random

from magic.spell.elemental.earth_shield import EarthShieldSpell
from magic.spell.elemental.freeze import FreezeSpell
from magic.spell.elemental.ice_shield import IceShieldSpell
from magic.spell.elemental.slice import SliceSpell
from magic.tests.helpers import AuraFixture, MockCaster


class EarthShieldFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_reduction = 0.75
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.shield_spell = EarthShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
        )
        self.damage = self.aura.magic.max.value / 2
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)


class IceShieldFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.damage_reduction = 0.50
        self.max_hits = random.randint(3, 5)
        self.duration = round(random.uniform(5.0, 10.0))
        self.caster = MockCaster()
        self.freeze_spell = FreezeSpell(duration=5.0, cast_delay_modifier=2.0)

        self.shield_spell = IceShieldSpell(
            reduction=self.damage_reduction,
            max_hits=self.max_hits,
            duration=self.duration,
            freeze_spell=self.freeze_spell,
            caster=self.caster,
        )

        self.damage = self.aura.magic.max.value / 4
        self.damage_spell = SliceSpell(damage=self.damage)
        self.damage_after_shield = self.damage * (1 - self.damage_reduction)
