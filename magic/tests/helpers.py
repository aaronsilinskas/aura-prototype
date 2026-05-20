import random

from magic import Aura
from magic.aura import AuraEvent, EventListener, Spell
from magic.caster import Caster


class AuraFixture:
    def __init__(self) -> None:
        self.min_magic: float = -1 * round(random.uniform(100.0, 200.0))
        self.max_magic: float = round(random.uniform(100.0, 200.0))
        self.cast_delay: float = round(random.uniform(3.0, 5.0))
        self.aura: Aura = Aura(
            min_magic=self.min_magic,
            max_magic=self.max_magic,
            cast_delay=self.cast_delay,
        )


class NoopSpell(Spell):
    """Base class for test spells with default implementations of abstract methods."""

    def update(self, aura, elapsed_time: float) -> bool:
        return False

    def on_level_changed(self, level: int) -> None:
        pass


class CapturedSpell:
    def __init__(self, spell: Spell, cast_type: str) -> None:
        self.spell = spell
        self.cast_type = cast_type


class MockCaster(Caster):
    def __init__(self) -> None:
        self.cast_spells: list[CapturedSpell] = []

    def cast_spell(self, spell: Spell, cast_type: str) -> None:
        self.cast_spells.append(CapturedSpell(spell, cast_type))

    def was_cast(self, spell: Spell, cast_type: str) -> bool:
        return any(
            captured.spell == spell and captured.cast_type == cast_type
            for captured in self.cast_spells
        )


class MockEventListener(EventListener):
    def __init__(self):
        self.events = []

    def on_spell_event(self, aura: Aura, event: AuraEvent) -> None:
        self.events.append((aura, event))

    def was_event_received(self, aura: Aura, event: AuraEvent) -> bool:
        return any(e is event and a is aura for a, e in self.events)

    @property
    def last_event(self) -> AuraEvent | None:
        if self.events:
            return self.events[-1][1]
        return None
