import math

from magic.aura import Aura, AuraEvent, DamageEvent, Spell, SpellTags
from magic.spell.elemental.elements import ElementTags
from magic.values import Duration

GRAVITY: float = 9.81  # m/s²


class AccelerationEvent(AuraEvent):
    """Event representing acceleration."""

    def __init__(
        self,
        x_accel: float,
        y_accel: float,
        z_accel: float,
        remove_gravity: bool = True,
    ) -> None:
        super().__init__()
        self.x_accel = x_accel
        self.y_accel = y_accel
        self.z_accel = z_accel

        self._accel_magnitude = math.sqrt(x_accel**2 + y_accel**2 + z_accel**2)
        if remove_gravity:
            # Subtract gravity
            self._accel_magnitude = max(0.0, self._accel_magnitude - GRAVITY)

    @property
    def accel_magnitude(self) -> float:
        return self._accel_magnitude


class WeightSpell(Spell):
    """Deals damage over time when acceleration above a threshold is detected.

    Level scaling: Increases the damage per second.
    """

    def __init__(
        self, acceleration_threshold: float, damage_per_second: float, duration: float
    ) -> None:
        super().__init__([SpellTags.DEBUFF, ElementTags.GRAVITY])
        self.duration = Duration(duration)
        self.acceleration_threshold = acceleration_threshold
        self._base_damage_per_second = damage_per_second
        self.damage_per_second = damage_per_second
        self.movement_detected = False

    def update(self, aura: Aura, elapsed_time: float) -> bool:
        # if movement was detected above threshold, apply damage
        if self.movement_detected:
            damage = self.damage_per_second * min(elapsed_time, self.duration.remaining)
            aura.process_event(DamageEvent(damage))

        return self.duration.update(elapsed_time)

    def modify_event(self, aura: "Aura", event: AuraEvent) -> None:
        if isinstance(event, AccelerationEvent):
            self.movement_detected = event.accel_magnitude > self.acceleration_threshold

    def on_level_changed(self, level: int) -> None:
        self.damage_per_second = Spell.LEVEL_SCALER.scale_value(self._base_damage_per_second, level)
