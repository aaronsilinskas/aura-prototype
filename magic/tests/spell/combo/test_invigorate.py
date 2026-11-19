import pytest

from magic.spell.combo.combo import SpellCombinations
from magic.spell.combo.invigorate import InvigorateCombination
from magic.spell.elemental.regen import RegenSpell
from magic.tests.helpers import AuraFixture


class InvigorateFixture(AuraFixture):
    def __init__(self) -> None:
        super().__init__()
        self.combos = SpellCombinations()
        self.aura.event_listeners.append(self.combos)

        self.original_max_magic = self.aura.magic.max.value
        self.max_magic_multiplier = 1.5
        self.duration = 10.0
        self.invigorate_combo = InvigorateCombination(self.max_magic_multiplier, self.duration)
        self.combos.add(self.invigorate_combo)
        self.regen_duration = 5.0


@pytest.fixture
def fixture() -> InvigorateFixture:
    return InvigorateFixture()


def test_invigorate_triggers_with_three_regen_spells(fixture: InvigorateFixture):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=10.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=fixture.regen_duration))

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)


def test_invigorate_does_not_trigger_with_two_regen_spells(fixture: InvigorateFixture):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=fixture.regen_duration))

    assert aura.magic.max.value == pytest.approx(original_max_magic)


def test_invigorate_does_not_trigger_with_one_regen_spell(fixture: InvigorateFixture):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value

    aura.add_spell(RegenSpell(regen_rate=7.0, duration=fixture.regen_duration))

    assert aura.magic.max.value == pytest.approx(original_max_magic)


def test_invigorate_does_not_trigger_with_no_regen_spells(fixture: InvigorateFixture):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value

    assert aura.magic.max.value == pytest.approx(original_max_magic)


def test_invigorate_modifier_expires_after_regen_and_duration(
    fixture: InvigorateFixture,
):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value
    regen_duration = 2.0

    regen1 = RegenSpell(regen_rate=5.0, duration=regen_duration)
    regen2 = RegenSpell(regen_rate=10.0, duration=regen_duration)
    regen3 = RegenSpell(regen_rate=8.0, duration=regen_duration)

    aura.add_spell(regen1)
    aura.add_spell(regen2)
    aura.add_spell(regen3)

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)

    aura.update(regen_duration + 1.0)

    assert len(aura.spells.get_by_class(RegenSpell)) == 0

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)

    aura.update(fixture.duration)

    assert aura.magic.max.value == pytest.approx(original_max_magic)


def test_invigorate_refreshes_when_regen_spells_return_to_three(
    fixture: InvigorateFixture,
):
    aura = fixture.aura
    original_max_magic = aura.magic.max.value

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=1))
    aura.add_spell(RegenSpell(regen_rate=5.0, duration=5))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=5))

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)

    aura.update(4)

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)

    aura.add_spell(RegenSpell(regen_rate=12.0, duration=5))
    aura.update(8)

    assert aura.magic.max.value == pytest.approx(original_max_magic * fixture.max_magic_multiplier)


def test_invigorate_check_returns_true_when_triggered(fixture: InvigorateFixture):
    standalone_combo = InvigorateCombination(fixture.max_magic_multiplier, fixture.duration)
    aura = fixture.aura

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=10.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=fixture.regen_duration))

    result = standalone_combo.check(aura)

    assert result is True


def test_invigorate_check_returns_false_when_already_applied(
    fixture: InvigorateFixture,
):
    standalone_combo = InvigorateCombination(fixture.max_magic_multiplier, fixture.duration)
    aura = fixture.aura

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=10.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=fixture.regen_duration))

    standalone_combo.check(aura)

    result = standalone_combo.check(aura)

    assert result is False


def test_invigorate_check_returns_false_with_insufficient_regen_spells(
    fixture: InvigorateFixture,
):
    standalone_combo = InvigorateCombination(fixture.max_magic_multiplier, fixture.duration)
    aura = fixture.aura

    aura.add_spell(RegenSpell(regen_rate=5.0, duration=fixture.regen_duration))
    aura.add_spell(RegenSpell(regen_rate=8.0, duration=fixture.regen_duration))

    result = standalone_combo.check(aura)

    assert result is False
