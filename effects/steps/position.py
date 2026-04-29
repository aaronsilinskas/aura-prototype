from __future__ import annotations

from effects.effect import EffectState, EffectStep, EffectTimer, SharedStateKey
from effects.value import DynamicValue, Range, ValueGenerator


class SetPositionStep(EffectStep):
    """Offsets the sampling position by a fixed or dynamic amount each frame."""

    def __init__(self, position: DynamicValue):
        self.position = position

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        state.set_step_data(self, ValueGenerator.resolve(self.position))
        return True

    def adjust_position(self, state: EffectState, position: float) -> float:
        return (position + (state.get_step_data(self, float) or 0.0)) % 1.0


def set_position(position: DynamicValue) -> EffectStep:
    """Return a step that shifts the sampling position by ``position`` each frame."""
    return SetPositionStep(position)


class VelocitySharedData:
    """Shared rotational state written by ``RotateStep`` and ``AccelerateStep``.

    Stored in ``EffectState`` under a single key so that steps like
    ``AccelerateStep`` and ``FaceForwardStep`` can read the current speed and
    accumulated offset without being coupled to a specific ``RotateStep``
    instance.
    """

    __slots__ = ("offset", "rotations_per_second")

    _VELOCITY_SHARED_KEY = SharedStateKey()

    def __init__(self) -> None:
        self.rotations_per_second: float = 0.0
        self.offset: float = 0.0

    @staticmethod
    def get(state: EffectState) -> VelocitySharedData:
        data = state.get_shared_data(
            VelocitySharedData._VELOCITY_SHARED_KEY, VelocitySharedData
        )
        if data is None:
            data = VelocitySharedData()
            state.set_shared_data(VelocitySharedData._VELOCITY_SHARED_KEY, data)

        return data


class RotateStep(EffectStep):
    """Continuously rotates the sampling position at a given speed.

    Accumulates a position offset each frame based on ``rotations_per_second``
    and writes velocity data to ``VelocitySharedData`` so that downstream steps
    like ``AccelerateStep`` and ``FaceForwardStep`` can read the current speed.
    """

    def __init__(self, rotations_per_second: DynamicValue):
        self.rotations_per_second = rotations_per_second

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        offset = state.get_step_data(self, float)
        if offset is None:
            offset = 0.0

        rps_value = ValueGenerator.resolve(self.rotations_per_second)

        offset = (offset + rps_value * timer.elapsed) % 1.0
        state.set_step_data(self, offset)

        # Update shared velocity data for steps that need to know current speed, direction, etc.
        velocity_data = VelocitySharedData.get(state)
        velocity_data.rotations_per_second = rps_value
        velocity_data.offset = offset

        return True

    def adjust_position(self, state: EffectState, position: float) -> float:
        return position + (state.get_step_data(self, float) or 0.0)


def rotate(rotations_per_second: DynamicValue) -> EffectStep:
    """Return a step that rotates the sampling position at ``rotations_per_second``."""
    return RotateStep(rotations_per_second)


class AccelerateStep(EffectStep):
    """Interpolates rotational speed from a start to an end value over the step's timer duration.

    Reads ``VelocitySharedData`` to seed the initial speed when ``start`` is
    ``None``, allowing a smooth hand-off from a preceding ``RotateStep`` or ``AccelerateStep``.
    """

    def __init__(
        self,
        start: DynamicValue | None = None,
        end: DynamicValue = 1.0,
        direction: DynamicValue | None = None,
    ):
        self.start = start
        self.end = end
        self.direction = direction

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        speed_range = state.get_step_data(self, Range)
        if speed_range is None:
            if self.start is not None:
                start_speed = ValueGenerator.resolve(self.start)
            else:
                start_speed = VelocitySharedData.get(state).rotations_per_second

            end_speed = ValueGenerator.resolve(self.end)

            if self.direction is not None:
                direction_value = ValueGenerator.resolve(self.direction)
                start_speed = abs(start_speed)
                end_speed = abs(end_speed)
                if direction_value < 0:
                    start_speed *= -1
                    end_speed *= -1

            speed_range = Range(start_speed, end_speed)
            state.set_step_data(self, speed_range)
        speed = speed_range.lerp(timer.progress)

        velocity_data = VelocitySharedData.get(state)
        velocity_data.rotations_per_second = speed
        velocity_data.offset = (velocity_data.offset + speed * timer.elapsed) % 1.0

        if timer.progress >= 1.0:
            state.remove_step_data(self)

        return True

    def adjust_position(self, state: EffectState, position: float) -> float:
        velocity_data = VelocitySharedData.get(state)
        return (position + velocity_data.offset) % 1.0


def accelerate(
    start: DynamicValue | None = None,
    end: DynamicValue = 1.0,
    direction: DynamicValue | None = None,
) -> EffectStep:
    """Return a step that ramps rotational speed from ``start`` to ``end``."""
    return AccelerateStep(start, end, direction)


class FaceForwardStep(EffectStep):
    """Flips the sampling direction so the effect always faces the direction of motion.

    Reads ``VelocitySharedData`` — when ``rotations_per_second`` is negative,
    the position is mirrored so the effect head leads rather than trails.
    """

    def update(self, state: EffectState, timer: EffectTimer) -> bool:
        return True

    def adjust_position(self, state: EffectState, position: float) -> float:
        velocity_data = VelocitySharedData.get(state)
        if velocity_data.rotations_per_second < 0:
            position = 1.0 - position

        return position


def face_forward() -> EffectStep:
    """Return a step that mirrors the sampling direction when moving in reverse."""
    return FaceForwardStep()
