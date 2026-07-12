from __future__ import annotations

try:
    from typing import Final
except ImportError:
    pass

import adafruit_drv2605  # type: ignore[import]

from effects.effect import Effect, HapticPattern
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectReceipt, Scope

# Maps HapticPattern constants to adafruit_drv2605 Effect/Pause objects.
# Effect constants are offset from DRV2605L hardware IDs; the mapping here
# translates them back to the correct waveform IDs.
_DRV2605L_EFFECT_MAP: Final = {
    HapticPattern.STRONG_CLICK: adafruit_drv2605.Effect(1),
    HapticPattern.SHARP_CLICK: adafruit_drv2605.Effect(4),
    HapticPattern.SOFT_BUMP: adafruit_drv2605.Effect(7),
    HapticPattern.DOUBLE_CLICK: adafruit_drv2605.Effect(10),
    HapticPattern.TRIPLE_CLICK: adafruit_drv2605.Effect(12),
    HapticPattern.STRONG_BUZZ: adafruit_drv2605.Effect(14),
    HapticPattern.PAUSE_250: adafruit_drv2605.Pause(0.25),
    HapticPattern.PAUSE_500: adafruit_drv2605.Pause(0.5),
    HapticPattern.PAUSE_1000: adafruit_drv2605.Pause(1.0),
}

_MAX_SEQUENCE_LEN: Final = 8

# Sentinel used to clear remaining driver sequence slots after a shorter sequence is written.
_EFFECT_ZERO: Final = adafruit_drv2605.Effect(0)


class Drv2605EffectOutput(EffectOutput):
    """EffectOutput that drives the DRV2605L haptic controller in response to game events.

    Registered on all scopes with ``receives_pixels = False`` — receives
    ``handle_event`` calls for every effect without incurring pixel buffer allocation.

    A new event always interrupts the current haptic pattern — writing the new sequence
    and calling ``driver.play()`` is sufficient; the hardware restarts immediately.

    ``flush()`` cuts the sequence short if the active receipt is externally stopped.
    The DRV2605L self-terminates after its sequence, so no natural-completion cleanup
    is needed.

    Args:
        driver: A configured ``adafruit_drv2605.DRV2605`` instance. Injected at
            construction so setup code remains in ``device_builder.py`` and this class
            stays testable.
    """

    __slots__ = ("_active_receipt", "_driver")

    def __init__(self, driver: object) -> None:
        super().__init__(receives_pixels=False)
        self.min_resolution = 1
        self.scopes = [Scope.ALL]
        self._driver = driver
        self._active_receipt: EffectReceipt | None = None

    def handle_event(
        self,
        event: EffectEvent,
        scope_keys: frozenset[str],
        effect: Effect,
        receipt: EffectReceipt,
    ) -> None:
        if effect.haptic is None:
            return
        config = effect.haptic.patterns.get(event.verb)
        if config is None:
            return

        sequence = config.sequence
        if len(sequence) > _MAX_SEQUENCE_LEN:
            n = len(sequence)
            msg = f"HapticPattern.sequence length {n} exceeds maximum {_MAX_SEQUENCE_LEN}"
            raise ValueError(msg)

        for i in range(len(sequence)):
            self._driver.sequence[i] = _DRV2605L_EFFECT_MAP[sequence[i]]

        for i in range(len(sequence), _MAX_SEQUENCE_LEN):
            self._driver.sequence[i] = _EFFECT_ZERO

        self._active_receipt = receipt
        self._driver.play()

    def flush(self) -> None:
        if self._active_receipt is not None and self._active_receipt.is_stopped():
            self._driver.stop()
            self._active_receipt = None
