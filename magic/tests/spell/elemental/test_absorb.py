import pytest

from magic.aura import Spell, SpellTags
from magic.spell.elemental.absorb import AbsorbSpell
from magic.tests.helpers import AuraFixture, NoopSpell


class DebuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[SpellTags.DEBUFF])


class BuffSpell(NoopSpell):
    def __init__(self) -> None:
        super().__init__(tags=[SpellTags.BUFF])


class AbsorbFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.duration = 10.0
        self.absorb_spell = AbsorbSpell(duration=self.duration)


@pytest.fixture
def fixture() -> AbsorbFixture:
    return AbsorbFixture()


def test_absorb_removes_single_debuff_on_add(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)

    assert debuff not in list(aura.spells)
    assert fixture.absorb_spell not in list(aura.spells)


def test_absorb_removes_itself_after_absorb_count_depleted(
    fixture: AbsorbFixture,
) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    assert fixture.absorb_spell not in list(aura.spells)

    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff2 in list(aura.spells)


def test_absorb_expires_after_duration(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    aura.update(fixture.duration + 1.0)

    assert fixture.absorb_spell not in list(aura.spells)


def test_absorb_does_not_remove_buffs(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    buff = BuffSpell()
    aura.add_spell(buff)
    aura.update(0.1)

    assert buff in list(aura.spells)
    assert fixture.absorb_spell in list(aura.spells)


def test_absorb_level_scaling(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    absorb_level_3 = AbsorbSpell(duration=10.0)
    absorb_level_3.level = 3
    aura.add_spell(absorb_level_3)

    # round(1 * (1 + 0.25 * (3 - 1))) = round(1.5) = 2
    expected_count = round(Spell.LEVEL_SCALER.scale_value(1, 3))
    assert expected_count == 2

    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    assert debuff1 not in list(aura.spells)
    assert absorb_level_3 in list(aura.spells)

    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff2 not in list(aura.spells)
    assert absorb_level_3 not in list(aura.spells)

    debuff3 = DebuffSpell()
    aura.add_spell(debuff3)
    aura.update(0.1)

    assert debuff3 in list(aura.spells)


def test_absorb_higher_level_scaling(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    absorb_level_5 = AbsorbSpell(duration=10.0)
    absorb_level_5.level = 10
    aura.add_spell(absorb_level_5)

    # round(1 * (1 + 0.25 * (10 - 1))) = round(3.25) = 3
    expected_count = round(Spell.LEVEL_SCALER.scale_value(1, 10))
    assert expected_count == 3

    for _ in range(expected_count):
        debuff = DebuffSpell()
        aura.add_spell(debuff)
        aura.update(0.1)
        assert debuff not in list(aura.spells)

    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)
    assert debuff in list(aura.spells)


def test_absorb_multiple_debuffs_simultaneously(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    absorb = AbsorbSpell(duration=10.0)
    absorb.level = 3
    aura.add_spell(absorb)

    debuff1 = DebuffSpell()
    debuff2 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff1 not in list(aura.spells)
    assert debuff2 not in list(aura.spells)
    assert absorb not in list(aura.spells)


def test_absorb_does_not_absorb_after_depleted(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    debuff1 = DebuffSpell()
    aura.add_spell(debuff1)
    aura.update(0.1)

    assert fixture.absorb_spell not in list(aura.spells)

    debuff2 = DebuffSpell()
    aura.add_spell(debuff2)
    aura.update(0.1)

    assert debuff2 in list(aura.spells)


def test_absorb_removes_itself_when_count_zero(fixture: AbsorbFixture) -> None:
    aura = fixture.aura

    aura.add_spell(fixture.absorb_spell)

    debuff = DebuffSpell()
    aura.add_spell(debuff)
    aura.update(0.1)

    # Absorb count is now 0, next update should remove it
    aura.update(0.1)

    assert fixture.absorb_spell not in list(aura.spells)
