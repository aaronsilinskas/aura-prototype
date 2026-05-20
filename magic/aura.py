try:
    from typing import TypeVar

    T = TypeVar("T")
except ImportError:
    pass

from magic.values import MinMaxValue, ValueWithModifiers


class SpellLevelScaler:
    """Scaling logic for spell levels."""

    def __init__(
        self, value_coefficient: float = 0.25, percentage_coefficient: float = 0.05
    ) -> None:
        """Initializes the coefficients for this level scaler.

        Args:
            value_coefficient (float, optional): The coefficient for scaling values.
                Defaults to 0.25.
            percentage_coefficient (float, optional): The coefficient for scaling percentages.
                Defaults to 0.05.
        """
        self._value_coefficient = max(value_coefficient, 0)
        self._percentage_coefficient = max(percentage_coefficient, 0)

    def scale_value(self, value: float, level: int) -> float:
        """Scales a value based on the spell's level and the value coefficient.
        Increases the base value by the value coefficient per level.
        """
        return value * (1 + self._value_coefficient * (level - 1))

    def scale_percentage(self, base_percentage: float, level: int) -> float:
        """Scales a percentage value based on the spell's level and the percentage coefficient.
        Adds the percentage coefficient to the base percentage per level.
        Clamps the value between 0 and 1."""
        return min(base_percentage + self._percentage_coefficient * (level - 1), 1)


class Spell:
    """Base class for all spells."""

    LEVEL_SCALER = SpellLevelScaler()
    """Shared level scaler for all spells. Overridable if needed."""

    def __init__(self, tags: list[str]) -> None:
        self.name: str = self.__class__.__name__.replace("Spell", "")
        self._tags: list[str] = tags
        self._level: int = 1

    def start(self, aura: "Aura") -> None:
        """Called when the spell is added to the aura. Can be used to set up initial state.
        Note: This is mainly used for passive modifiers like cast delay or resistances that are
        removed when the spell is stopped. Do not apply damage, healing, or other immediate
        effects here."""
        pass

    def update(self, aura: "Aura", elapsed_time: float) -> bool:
        """Update the spell. Return True if the spell should be removed from the aura."""
        raise NotImplementedError()

    def stop(self, aura: "Aura") -> None:
        """Called when the spell is removed from the aura. Can be used to clean up state."""
        pass

    def modify_event(self, aura: "Aura", event: "AuraEvent") -> None:
        """Modify an incoming event if needed, will only be called for active spells."""
        pass

    def on_level_changed(self, level: int) -> None:
        """Called when the spell's level is changed, allowing for adjustments based on level."""
        raise NotImplementedError()

    @property
    def tags(self):
        return iter(self._tags)

    @property
    def level(self) -> int:
        """Returns the current level of the spell."""
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        """Sets the level of the spell, affecting its potency."""
        self._level = max(1, value)
        self.on_level_changed(self._level)


class SpellTags:
    """String constants for categorising spells by role."""

    SHIELD = "SHIELD"
    BUFF = "BUFF"
    DEBUFF = "DEBUFF"


class AuraEvent:
    """Base class for events affecting the aura."""

    def __init__(self) -> None:
        self._canceled: bool = False

    @property
    def is_canceled(self) -> bool:
        return self._canceled

    @is_canceled.setter
    def is_canceled(self, value: bool) -> None:
        self._canceled = value


class DamageEvent(AuraEvent):
    """Event representing damage taken."""

    def __init__(self, amount: float) -> None:
        """Initializes a damage event with a specific amount."""
        super().__init__()
        self.amount = max(0, amount)


class HealEvent(AuraEvent):
    """Event representing healing received."""

    def __init__(self, amount: float) -> None:
        """Initializes a heal event with a specific amount."""
        super().__init__()
        self.amount = max(0, amount)


class CastEvent(AuraEvent):
    """Event representing a spell cast attempt."""

    def __init__(self, spell: Spell) -> None:
        """Initializes a cast event."""
        super().__init__()
        self.spell = spell


class AddSpellEvent(AuraEvent):
    """Event representing a spell being added to the aura."""

    def __init__(self, spell: Spell) -> None:
        """Initializes an adding spell event."""
        super().__init__()
        self.spell = spell


class RemoveSpellEvent(AuraEvent):
    """Event representing a spell being removed from the aura."""

    def __init__(self, spell: Spell) -> None:
        """Initializes a removing spell event."""
        super().__init__()
        self.spell = spell


class EventListener:
    """Interface for objects that listen to aura events."""

    def on_spell_event(self, aura: "Aura", event: AuraEvent) -> None:
        """Called when an event occurs in the aura."""
        pass


class Spells:
    """A collection manager for Spell objects."""

    def __init__(self, spells: list[Spell]) -> None:
        self._spells: list[Spell] = spells

    def get_by_name(self, name: str) -> list[Spell]:
        """Finds a spell by its name."""
        return [spell for spell in self._spells if spell.name == name]

    def get_by_tag(self, *tags: str) -> list[Spell]:
        """Finds spells that have all of the specified tags."""
        if not tags:
            return []
        return [spell for spell in self._spells if all(tag in spell.tags for tag in tags)]

    def get_by_class(self, cls: "type[T]") -> "list[T]":
        """Finds spells by their class type."""
        matching = []
        for spell in self._spells:
            if isinstance(spell, cls):
                matching.append(spell)

        return matching

    def __len__(self) -> int:
        return len(self._spells)

    def __iter__(self):
        return iter(self._spells)


class Aura:
    """Manages the active spells and magic level of an entity.

    Handles incoming events (damage/healing) and updates spells over time.
    """

    def __init__(self, min_magic: float, max_magic: float, cast_delay: float) -> None:
        """Initialize the Aura with magic bounds and cast delay.

        Args:
            min_magic: The minimum value the magic attribute can reach.
            max_magic: The maximum value the magic attribute can reach.
            cast_delay: The base cast delay in seconds.
        """
        self.magic = MinMaxValue(value=max_magic, min=min_magic, max=max_magic)
        self._spell_list: list[Spell] = []
        self._spells = Spells(self._spell_list)
        self._cast_delay = ValueWithModifiers(base_value=cast_delay)
        self._event_listeners: list[EventListener] = []

    def add_spell(self, spell: Spell) -> None:
        """Adds a spell to the aura and starts it.

        Args:
            spell: The spell to add.
        """
        self.process_event(AddSpellEvent(spell))

    def remove_spell(self, spell: Spell) -> None:
        """Removes a spell from the aura and stops it.

        Args:
            spell: The spell to remove.
        """
        self.process_event(RemoveSpellEvent(spell))

    def cast_spell(self, spell: Spell) -> None:
        """Attempts to cast a spell, allow the spell and other active spells to react to it.

        Args:
            spell: The spell to cast.
        """
        self.process_event(CastEvent(spell))

    def process_event(self, event: AuraEvent) -> None:
        """Processes an incoming event through all active spells.

        If an event is canceled by a spell, it is not applied to the magic value.

        Args:
            event: The incoming event to process.
        """
        for spell in self.spells:
            spell.modify_event(self, event)
            if event.is_canceled:
                return

        self._apply_event(event)
        for listener in self._event_listeners:
            listener.on_spell_event(self, event)

    def _apply_event(self, event: AuraEvent) -> None:
        """Applies the event to the magic value.

        Args:
            event: The event to apply.
        """
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
        """Updates the aura state, magic, and spells.

        Args:
            elapsed_time: The time passed since the last update.
        """
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
        """Returns the active spells collection."""
        return self._spells

    @property
    def cast_delay(self) -> ValueWithModifiers:
        """Returns the current cast delay including modifiers."""
        return self._cast_delay

    @property
    def event_listeners(self) -> list[EventListener]:
        """Returns the list of event listeners.

        These listeners will be notified on events after the event is processed
        by active spells and the Aura.
        """
        return self._event_listeners
