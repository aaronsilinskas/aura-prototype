import pytest
from magic.aura import SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.spell.elemental.warmth import WarmthSpell
from magic.tests.helpers import AuraFixture, NoopSpell


# Test spell classes
class WaterDebuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[ElementTags.WATER, SpellTags.DEBUFF])


class IceDebuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[ElementTags.ICE, SpellTags.DEBUFF])


class FireDebuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[ElementTags.FIRE, SpellTags.DEBUFF])


class WaterBuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[ElementTags.WATER, SpellTags.BUFF])


class IceBuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[ElementTags.ICE, SpellTags.BUFF])


@pytest.fixture
def fixture() -> AuraFixture:
    return AuraFixture()


def test_warmth_removes_water_debuffs(fixture: AuraFixture) -> None:
    aura = fixture.aura

    water_debuff = WaterDebuffSpell()
    aura.add_spell(water_debuff)

    # Verify debuff is present
    assert water_debuff in list(aura.spells)

    # Add warmth spell
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Update to trigger warmth spell
    aura.update(0.1)

    # Water debuff should be removed, warmth should also be removed (instant effect)
    assert water_debuff not in list(aura.spells)
    assert warmth not in list(aura.spells)
    assert len(list(aura.spells)) == 0


def test_warmth_removes_ice_debuffs(fixture: AuraFixture) -> None:
    aura = fixture.aura

    ice_debuff = IceDebuffSpell()
    aura.add_spell(ice_debuff)

    # Verify debuff is present
    assert ice_debuff in list(aura.spells)

    # Add warmth spell
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Update to trigger warmth spell
    aura.update(0.1)

    # Ice debuff should be removed, warmth should also be removed (instant effect)
    assert ice_debuff not in list(aura.spells)
    assert warmth not in list(aura.spells)
    assert len(list(aura.spells)) == 0


def test_warmth_removes_multiple_water_and_ice_debuffs(fixture: AuraFixture) -> None:
    aura = fixture.aura

    water_debuff1 = WaterDebuffSpell()
    water_debuff2 = WaterDebuffSpell()
    ice_debuff1 = IceDebuffSpell()
    ice_debuff2 = IceDebuffSpell()

    aura.add_spell(water_debuff1)
    aura.add_spell(water_debuff2)
    aura.add_spell(ice_debuff1)
    aura.add_spell(ice_debuff2)

    # Verify all debuffs are present
    assert len(list(aura.spells)) == 4

    # Add warmth spell
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Update to trigger warmth spell
    aura.update(0.1)

    # All debuffs and warmth should be removed
    assert len(list(aura.spells)) == 0


def test_warmth_does_not_remove_other_debuffs(fixture: AuraFixture) -> None:
    aura = fixture.aura

    # Create fire debuff spell (should not be removed)
    fire_debuff = FireDebuffSpell()
    aura.add_spell(fire_debuff)

    # Add warmth spell
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Update to trigger warmth spell
    aura.update(0.1)

    # Fire debuff should remain, warmth should be removed
    assert fire_debuff in list(aura.spells)
    assert warmth not in list(aura.spells)
    assert len(list(aura.spells)) == 1


def test_warmth_does_not_remove_water_or_ice_buffs(fixture: AuraFixture) -> None:
    aura = fixture.aura

    water_buff = WaterBuffSpell()
    ice_buff = IceBuffSpell()
    aura.add_spell(water_buff)
    aura.add_spell(ice_buff)

    # Add warmth spell
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Update to trigger warmth spell
    aura.update(0.1)

    # Buffs should remain, warmth should be removed
    assert water_buff in list(aura.spells)
    assert ice_buff in list(aura.spells)
    assert warmth not in list(aura.spells)
    assert len(list(aura.spells)) == 2


def test_warmth_removes_itself_immediately(fixture: AuraFixture) -> None:
    aura = fixture.aura

    # Add warmth spell with no debuffs present
    warmth = WarmthSpell()
    aura.add_spell(warmth)

    # Verify warmth is added
    assert warmth in list(aura.spells)

    # Update to trigger warmth spell
    aura.update(0.1)

    # Warmth should remove itself immediately
    assert warmth not in list(aura.spells)
    assert len(list(aura.spells)) == 0
