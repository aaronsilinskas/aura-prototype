from __future__ import annotations

from magic.values import MinMaxValue, ValueWithModifiers

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Final, TypeVar

    T = TypeVar("T")


class SpellLevelScaler:
    def __init__(
        self, value_coefficient: float = 0.25, percentage_coefficient: float = 0.05
    ) -> None:
        self._value_coefficient = max(value_coefficient, 0)
        self._percentage_coefficient = max(percentage_coefficient, 0)

    def scale_value(self, value: float, level: int) -> float:
        return value * (1 + self._value_coefficient * (level - 1))

    def scale_percentage(self, base_percentage: float, level: int) -> float:
        return min(base_percentage + self._percentage_coefficient * (level - 1), 1)


class Spell:
    LEVEL_SCALER = SpellLevelScaler()

    def __init__(self, tags: list[str]) -> None:
        self.name: str = self.__class__.__name__.replace("Spell", "")
        self._tags: list[str] = tags
        self._level: int = 1

    def start(self, aura: Aura) -> None:
        """Called when the spell is added to the aura, to apply passive modifiers such as
        cast delay or resistances that ``stop()`` removes.

        Do not apply damage, healing, or other immediate effects here.
        """
        pass

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        """Advances the spell; returns ``True`` when it should be removed from the aura."""
        raise NotImplementedError()

    def stop(self, aura: Aura) -> None:
        """Called when the spell is removed from the aura."""
        pass

    def modify_event(self, aura: Aura, event: AuraEvent) -> None:
        """Called with each incoming event while the spell is active; may change or cancel it."""
        pass

    def on_level_changed(self, level: int) -> None:
        raise NotImplementedError()

    @property
    def tags(self) -> Iterator[str]:
        return iter(self._tags)

    @property
    def level(self) -> int:
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        self._level = max(1, value)
        self.on_level_changed(self._level)


class SpellTags:
    SHIELD: Final = "SHIELD"
    BUFF: Final = "BUFF"
    DEBUFF: Final = "DEBUFF"


class AuraEvent:
    def __init__(self) -> None:
        self._canceled: bool = False

    @property
    def is_canceled(self) -> bool:
        return self._canceled

    @is_canceled.setter
    def is_canceled(self, value: bool) -> None:
        self._canceled = value


class DamageEvent(AuraEvent):
    def __init__(self, amount: float) -> None:
        super().__init__()
        self.amount = max(0, amount)


class HealEvent(AuraEvent):
    def __init__(self, amount: float) -> None:
        super().__init__()
        self.amount = max(0, amount)


class CastEvent(AuraEvent):
    def __init__(self, spell: Spell) -> None:
        super().__init__()
        self.spell = spell


class AddSpellEvent(AuraEvent):
    def __init__(self, spell: Spell) -> None:
        super().__init__()
        self.spell = spell


class RemoveSpellEvent(AuraEvent):
    def __init__(self, spell: Spell) -> None:
        super().__init__()
        self.spell = spell


class EventListener:
    def on_spell_event(self, aura: Aura, event: AuraEvent) -> None:
        pass


class Spells:
    def __init__(self, spells: list[Spell]) -> None:
        self._spells: list[Spell] = spells

    def get_by_name(self, name: str) -> list[Spell]:
        return [spell for spell in self._spells if spell.name == name]

    def get_by_tag(self, *tags: str) -> list[Spell]:
        """Finds spells that have all of the specified tags."""
        if not tags:
            return []
        return [spell for spell in self._spells if all(tag in spell.tags for tag in tags)]

    def get_by_class(self, cls: type[T]) -> list[T]:
        matching: list[T] = []
        for spell in self._spells:
            if isinstance(spell, cls):
                matching.append(spell)

        return matching

    def __len__(self) -> int:
        return len(self._spells)

    def __iter__(self) -> Iterator[Spell]:
        return iter(self._spells)


class Aura:
    """Manages the active spells and magic level of an entity."""

    def __init__(self, min_magic: float, max_magic: float, cast_delay: float) -> None:
        self.magic = MinMaxValue(value=max_magic, min=min_magic, max=max_magic)
        self._spell_list: list[Spell] = []
        self._spells = Spells(self._spell_list)
        self._cast_delay = ValueWithModifiers(base_value=cast_delay)
        self._event_listeners: list[EventListener] = []

    def add_spell(self, spell: Spell) -> None:
        self.process_event(AddSpellEvent(spell))

    def remove_spell(self, spell: Spell) -> None:
        self.process_event(RemoveSpellEvent(spell))

    def cast_spell(self, spell: Spell) -> None:
        self.process_event(CastEvent(spell))

    def process_event(self, event: AuraEvent) -> None:
        """Passes ``event`` to each active spell; if one cancels it, it is neither
        applied nor sent to listeners."""
        for spell in self.spells:
            spell.modify_event(self, event)
            if event.is_canceled:
                return

        self._apply_event(event)
        for listener in self._event_listeners:
            listener.on_spell_event(self, event)

    def _apply_event(self, event: AuraEvent) -> None:
        if isinstance(event, DamageEvent):
            self.magic.value -= event.amount
        elif isinstance(event, HealEvent):
            self.magic.value += event.amount
        elif isinstance(event, AddSpellEvent):
            self._spell_list.append(event.spell)
            event.spell.start(self)
        elif isinstance(event, RemoveSpellEvent):
            self._spell_list.remove(event.spell)
            event.spell.stop(self)

    def update(self, elapsed_time: float) -> None:
        self.magic.update(elapsed_time)
        self._cast_delay.update(elapsed_time)

        spells_to_remove = []
        for spell in self.spells:
            should_remove = spell.update(self, elapsed_time)
            if should_remove:
                spells_to_remove.append(spell)
        for spell in spells_to_remove:
            self.remove_spell(spell)

    @property
    def spells(self) -> Spells:
        return self._spells

    @property
    def cast_delay(self) -> ValueWithModifiers:
        return self._cast_delay

    @property
    def event_listeners(self) -> list[EventListener]:
        """The registered listeners, notified after each event is processed by
        active spells and the Aura."""
        return self._event_listeners
