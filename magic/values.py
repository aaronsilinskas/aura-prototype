try:
    from typing import Callable
except ImportError:
    pass


class Duration:
    """A utility class for tracking a duration."""

    def __init__(self, length: float) -> None:
        """Initialize a Duration tracker.

        Args:
            length: The total length of the duration.
        """
        self._length: float = length
        self._elapsed: float = 0.0

    def update(self, elapsed_time: float) -> bool:
        """Update the elapsed time and check if the duration has expired.

        Args:
            elapsed_time: The amount of time passed since the last update.

        Returns:
            True if the duration has expired, False otherwise.
        """
        self._elapsed += elapsed_time

        return self.is_expired

    def reset(self) -> None:
        """Resets the elapsed time to zero."""
        self._elapsed = 0.0

    @property
    def length(self) -> float:
        """The total length of the duration."""
        return self._length

    @length.setter
    def length(self, value: float) -> None:
        """Sets the total length of the duration.

        Args:
            value: The new length of the duration.
        """
        self._length = value

    @property
    def elapsed(self) -> float:
        """The time elapsed since the start of the duration."""
        return self._elapsed

    @property
    def remaining(self) -> float:
        """The remaining time until the duration expires."""
        return max(0.0, self._length - self._elapsed)

    @property
    def is_expired(self) -> bool:
        """Whether the duration has expired."""
        return self._elapsed >= self._length


class ValueModifier:
    """Applies a temporary multiplier to a value."""

    def __init__(self, multiplier: float, duration: float) -> None:
        """Initializes the modifier with a multiplier and duration.

        Args:
            multiplier: The factor by which the value is multiplied.
            duration: The time in seconds the modifier lasts.
        """
        self._multiplier = multiplier
        self._duration = Duration(duration)

    def update(self, elapsed_time: float) -> bool:
        """Updates the elapsed time.

        Args:
            elapsed_time: The time passed since the last update.

        Returns:
            True if the modifier has expired, False otherwise.
        """
        return self._duration.update(elapsed_time)

    @property
    def multiplier(self) -> float:
        """Returns the multiplier."""
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value: float) -> None:
        """Sets the multiplier.

        Args:
            value: The new multiplier value.
        """
        self._multiplier = value

    @property
    def duration(self) -> Duration:
        """Returns the total duration."""
        return self._duration


class ValueModifiers:
    """Manages a collection of ValueModifiers and notifies an optional callback when the list changes."""

    def __init__(self, modifiers_changed: Callable | None = None) -> None:
        """Initializes the manager with a callback for list changes.

        Args:
            modifiers_changed: A callable to invoke when modifiers are added or removed.
        """
        self._modifiers: list[ValueModifier] = []
        self._modifiers_changed = modifiers_changed

    def _notify_modifiers_changed(self) -> None:
        if self._modifiers_changed:
            self._modifiers_changed()

    def add(self, modifier: ValueModifier) -> bool:
        """Adds a modifier to the list if it is not already present and triggers the callback.

        Args:
            modifier: The modifier to add.
        Returns:
            True if the modifier was added, False if it was already present.
        """
        if modifier not in self._modifiers:
            self._modifiers.append(modifier)
            self._notify_modifiers_changed()
            return True

        return False

    def remove(self, modifier: ValueModifier) -> None:
        """Removes a modifier from the list and triggers the callback.

        Args:
            modifier: The modifier to remove.
        """
        if modifier in self._modifiers:
            self._modifiers.remove(modifier)
            self._notify_modifiers_changed()

    def update(self, elapsed_time: float) -> None:
        """Updates all modifiers, removing expired ones and triggering the callback if changes occurred.

        Args:
            elapsed_time: The time passed since the last update.
        """
        modifiers_to_remove = []
        for modifier in self._modifiers:
            # If update returns True, the modifier has expired
            if modifier.update(elapsed_time):
                modifiers_to_remove.append(modifier)

        for modifier in modifiers_to_remove:
            self._modifiers.remove(modifier)

        if len(modifiers_to_remove) > 0:
            self._notify_modifiers_changed()

    def modify(self, base_value: float) -> float:
        """Applies all active modifiers to a base value.

        Args:
            base_value: The value to modify.

        Returns:
            The modified value.
        """
        modified_value = base_value
        for modifier in self._modifiers:
            modified_value *= modifier.multiplier

        return modified_value

    def __len__(self) -> int:
        """Returns the number of active modifiers."""
        return len(self._modifiers)

    def __iter__(self):
        """Returns an iterator over the active modifiers."""
        return iter(self._modifiers)


class ValueWithModifiers:
    """A value that can be modified by a set of multipliers."""

    def __init__(
        self, base_value: float = 0.0, value_changed: Callable | None = None
    ) -> None:
        """Initializes the value with modifiers.

        Args:
            value_changed: A callable to invoke when the value changes.
        """
        self._base: float = base_value
        self._value: float = base_value
        self._value_changed = value_changed
        self._modifiers: ValueModifiers = ValueModifiers(self._update_value)

    def _update_value(self) -> None:
        """Invokes the value changed callback if set."""
        self._value = self._modifiers.modify(self._base)
        if self._value_changed:
            self._value_changed()

    def update(self, elapsed_time: float) -> None:
        """Updates the modifiers.

        Args:
            elapsed_time: The time passed since the last update.
        """
        self._modifiers.update(elapsed_time)

    @property
    def base(self) -> float:
        """Returns the base value."""
        return self._base

    @base.setter
    def base(self, value: float) -> None:
        """Sets the base value."""
        self._base = value
        self._update_value()

    @property
    def modifiers(self) -> ValueModifiers:
        """Returns the modifiers manager."""
        return self._modifiers

    @property
    def value(self) -> float:
        """Returns the modified value."""
        return self._value


class MinMaxValue:
    """A value clamped between a minimum and a dynamic maximum."""

    def __init__(self, value: float, min: float, max: float) -> None:
        """Initializes the value with a clamped starting value.

        Args:
            value: The starting value.
            min: The minimum allowed value.
            max: The base maximum allowed value.
        """
        self._value = value
        self._min = min
        self._max = ValueWithModifiers(base_value=max, value_changed=self._clamp_value)

    def _clamp_value(self) -> None:
        """Clamps the current value between min and max."""
        self._value = max(self.min, min(self._value, self.max.value))

    def update(self, elapsed_time: float) -> None:
        """Updates the maximum modifiers.

        Args:
            elapsed_time: The time passed since the last update.
        """
        self._max.update(elapsed_time)

    @property
    def value(self) -> float:
        """Returns the current clamped value."""
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        """Sets the value, clamping it between min and max.

        Args:
            value: The value to set.
        """
        self._value = value
        self._clamp_value()

    @property
    def min(self) -> float:
        """Returns the minimum allowed value."""
        return self._min

    @min.setter
    def min(self, value: float) -> None:
        """Updates the minimum allowed value and clamps the current value if necessary.

        Args:
            value: The new minimum value.
        """
        self._min = value
        self._clamp_value()

    @property
    def max(self) -> ValueWithModifiers:
        """Returns the current maximum, considering active modifiers."""
        return self._max


class Counter:
    """A counter for tracking attributes like spell hits."""

    def __init__(self, max: int) -> None:
        """Initializes the counter."""
        self._max: int = max
        self._count: int = 0

    def increment(self) -> bool:
        """Increments the count by one. Returns True if max reached."""
        self._count = min(self._count + 1, self._max)

        return self._count >= self._max

    def reset(self) -> None:
        """Resets the count to zero."""
        self._count = 0

    @property
    def count(self) -> int:
        """Returns the current count."""
        return self._count

    @property
    def max(self) -> int:
        """Returns the maximum count allowed."""
        return self._max

    @property
    def is_max(self) -> bool:
        """Returns True if the current count has reached the maximum."""
        return self._count >= self._max
