from effects.effect import Effect, PixelBuffer
from engine.events import EffectEvent
from engine.state import EffectReceipt, ScopeValue


class EffectOutput:
    """Interface for sending rendered pixels and events to hardware outputs.

    Concrete subclasses must set in their __init__:
      - min_resolution: int  — minimum pixel count needed by this output.
      - scopes: list         — list of ScopeValue this output serves.
    """

    __slots__ = ("_receives_pixels", "min_resolution", "scopes")

    min_resolution: int
    scopes: list[ScopeValue]

    def __init__(self, receives_pixels: bool = True) -> None:
        self._receives_pixels = receives_pixels

    @property
    def receives_pixels(self) -> bool:
        """Whether this output expects pixel data.

        Non-pixel outputs (e.g. audio, event-only) pass ``receives_pixels=False``
        to ``super().__init__()`` to skip ``create_buffer`` calls, ``update_pixels``
        calls, and frame buffer allocation.  ``flush`` is still called
        unconditionally every tick.
        """
        return getattr(self, "_receives_pixels", True)

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        """Create a PixelBuffer sized for the given scope key's hardware region."""
        raise NotImplementedError

    def update_pixels(self, scope_key: str, buffer: PixelBuffer) -> None:
        """Receive one already-composed frame for this output for a single scope key.

        Called once per registered scope key per tick, with a single
        full-region buffer already merged from that scope's layered effects
        by the active ``MergeStrategy``. ``clear_pixels`` is the sole
        go-dark path — this method is not called when no effects are active
        for that key.
        """

    def flush(self) -> None:
        """Commit staged pixel data to hardware or other sinks.

        Called unconditionally once per tick, after ``update_pixels`` for this
        output. Concrete pixel outputs override this to flush their hardware
        buffer (e.g. ``strip.show()`` for NeoPixels). Audio and event outputs
        may leave this as a no-op.
        """

    def clear_pixels(self, scope_key: str) -> None:
        """Signal that the given scope key should go dark.

        Called when the last effect covering this key stops. Hardware outputs
        can override this to explicitly clear their buffer (e.g. write zeros to
        LEDs). Default is a no-op.
        """

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        """Handle an event triggered by an effect lifecycle or effect-triggered signal.

        Lifecycle events (start/stop) and effect-triggered signals all deliver
        an ``EffectEvent`` instance.
        """
