from effects.effect import EffectState, EffectTimer
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.effects.scope import ScopeValue
from engine.timer import Timer

_DEFAULT_RESOLUTION = 16


class EffectOutput:
    """Interface for sending rendered pixels and events to hardware outputs.

    Concrete subclasses must set in their __init__:
      - min_resolution: int  — minimum pixel count needed by this output.
      - scopes: list         — list of ScopeValue this output serves.
    """

    min_resolution: int
    scopes: list[ScopeValue]

    def create_buffer(self) -> PixelBuffer:
        """Create a PixelBuffer sized to this output's hardware pixel count."""
        raise NotImplementedError

    def update_pixels(self, frames: "list[tuple[PixelBuffer, EffectReceipt]]") -> None:
        """Receive rendered frames for this output.

        Called every update tick. Each element is a (PixelBuffer, EffectReceipt) tuple.
        Receives an empty list when no effects are active (signal to go dark).
        """
        pass

    def handle_event(self, event_name: str, scope: "ScopeValue", receipt: "EffectReceipt") -> None:
        """Handle an event triggered by an effect renderer."""
        pass


class EffectBuilder:
    """Factory interface for constructing ``EffectRenderer`` instances by name.

    Concrete implementations look up the named effect and return a renderer
    configured for the given ``RendererConfig``. Raise ``KeyError`` or
    ``ValueError`` for unregistered names.
    """

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        """Build an EffectRenderer for the named effect.

        Args:
            name: The registered effect name (e.g. ``"color.flash"``).
            config: Runtime configuration for the render pass. ``config.level``
                carries the universal intensity in ``[1, 10]``; ``config.options``
                carries any effect-specific parameters (e.g. duration, color).
                ``config.resolution`` describes the output hardware.

        Returns:
            A configured ``EffectRenderer`` ready to be paired with an
            ``EffectState`` and advanced each frame.
        """
        raise NotImplementedError


class EffectReceipt:
    """Opaque handle returned when an effect is started.

    Uniquely identifies a single running effect instance. Pass to
    ``stop_effect_by_receipt`` (issue #64) to stop exactly that instance.
    """

    __slots__ = ("id",)

    def __init__(self, effect_id: int) -> None:
        self.id: int = effect_id

    def __repr__(self) -> str:
        return f"EffectReceipt(id={self.id})"


class EffectControls:
    """Read-only effect-control interface exposed to game rules via GameState.

    Provides effect start/stop operations only. The update() tick is
    intentionally excluded so rules cannot advance the effect loop.
    """

    def set_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> "EffectReceipt":
        """Stop any effect(s) currently running in scope, then start name."""
        raise NotImplementedError

    def add_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> "EffectReceipt":
        """Start name in scope without stopping existing effects."""
        raise NotImplementedError

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all effects whose keys overlap scope."""
        raise NotImplementedError

    def stop_effect_by_receipt(self, receipt: "EffectReceipt") -> None:
        """Stop exactly the effect identified by receipt."""
        raise NotImplementedError


class EffectManager(EffectControls):
    """Manages running effects and routesrendered frames to registered outputs each tick.

    Update model:
      - Call ``update(timer)`` once per frame. Each unique renderer is
        advanced exactly once; outputs receive their frames in a second pass.
      - Outputs always receive a call, with an empty list when no effects
        are active (go-dark signal).
    State ownership:
      - Output buffers are created once per effect via ``EffectOutput.create_buffer``.
    """

    class _EffectEntry:
        __slots__ = ("keys", "name", "output_buffers", "receipt", "renderer", "scope", "state")

        def __init__(
            self,
            keys: tuple[str, ...],
            name: str,
            receipt: "EffectReceipt",
            output_buffers: list[PixelBuffer | None],
            renderer: EffectRenderer,
            scope: ScopeValue,
            state: EffectState,
        ) -> None:
            self.keys: tuple[str, ...] = keys
            self.name: str = name
            self.receipt: EffectReceipt = receipt
            self.output_buffers: list[PixelBuffer | None] = output_buffers
            self.renderer: EffectRenderer = renderer
            self.scope: ScopeValue = scope
            self.state: EffectState = state

        def __repr__(self) -> str:
            return (
                f"_EffectEntry(name={self.name!r}, receipt_id={self.receipt.id},"
                f" keys={self.keys!r})"
            )

    __slots__ = (
        "_builder",
        "_effects",
        "_frames",
        "_next_id",
        "_output_key_sets",
        "_outputs",
        "_timer",
    )

    def __init__(self, builder: EffectBuilder, outputs: list[EffectOutput]) -> None:
        self._builder: EffectBuilder = builder
        self._outputs: list[EffectOutput] = outputs
        self._effects: list[EffectManager._EffectEntry] = []
        self._next_id: int = 1
        self._timer: EffectTimer = EffectTimer()
        self._output_key_sets: list[frozenset[str]] = [
            frozenset(k for s in o.scopes for k in s.keys) for o in outputs
        ]
        self._frames: list[list[tuple[PixelBuffer, EffectReceipt]]] = [[] for _ in outputs]

    def _notify_listeners(
        self, event_name: str, scope_keys: set[str], scope: ScopeValue, receipt: "EffectReceipt"
    ) -> None:
        """Notify listeners registered for the given scope."""
        for output in self._outputs:
            for s in output.scopes:
                if any(k in scope_keys for k in s.keys):
                    output.handle_event(event_name, scope, receipt)
                    break

    def _build_effect(
        self,
        scope: ScopeValue,
        scope_key_set: set[str],
        name: str,
        level: int,
        options: dict[str, object],
    ) -> "EffectManager._EffectEntry":
        """Construct an EffectRenderer paired with a fresh EffectState."""
        receipt = EffectReceipt(self._next_id)
        self._next_id += 1

        def scoped_listener(event_name: str) -> None:
            self._notify_listeners(event_name, scope_key_set, scope, receipt)

        resolution = _DEFAULT_RESOLUTION
        output_buffers = []
        for i, output in enumerate(self._outputs):
            if any(k in self._output_key_sets[i] for k in scope_key_set):
                if output.min_resolution > resolution:
                    resolution = output.min_resolution
                output_buffers.append(output.create_buffer())
            else:
                output_buffers.append(None)
        config = RendererConfig(
            level=level, resolution=resolution, options=options, listeners=[scoped_listener]
        )
        renderer = self._builder(name, config)
        return EffectManager._EffectEntry(
            scope.keys, name, receipt, output_buffers, renderer, scope, EffectState()
        )

    def _append_new_effect(
        self,
        scope: ScopeValue,
        scope_key_set: set[str],
        name: str,
        level: int,
        options: dict[str, object],
    ) -> EffectReceipt:
        """Build, append, and return the receipt for a new effect entry."""
        entry = self._build_effect(scope, scope_key_set, name, level, options)
        self._effects.append(entry)
        return entry.receipt

    def _update_output_buffers(self, entry: "_EffectEntry") -> None:
        """Null out pre-allocated buffers for outputs no longer matched by entry.keys."""
        key_set = set(entry.keys)
        for i in range(len(self._outputs)):
            if entry.output_buffers[i] is not None and not any(
                k in self._output_key_sets[i] for k in key_set
            ):
                entry.output_buffers[i] = None

    def _remove_effects_in_scope(self, scope_key_set: set[str]) -> None:
        """Remove or narrow entries that overlap scope_key_set, firing stop events."""
        new_effects = []
        for entry in self._effects:
            remaining = tuple(k for k in entry.keys if k not in scope_key_set)
            if len(remaining) < len(entry.keys):
                self._notify_listeners(
                    f"{entry.name}.stop", scope_key_set, entry.scope, entry.receipt
                )
            if remaining:
                entry.keys = remaining
                self._update_output_buffers(entry)
                new_effects.append(entry)
        self._effects = new_effects

    def set_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        """Replace any running effect(s) in scope and start this one."""
        scope_key_set = set(scope.keys)
        self._remove_effects_in_scope(scope_key_set)
        receipt = self._append_new_effect(scope, scope_key_set, name, level, options)
        self._notify_listeners(f"{name}.start", scope_key_set, scope, receipt)
        return receipt

    def add_effect(
        self, scope: ScopeValue, name: str, level: int, options: dict[str, object]
    ) -> EffectReceipt:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        scope_key_set = set(scope.keys)
        receipt = self._append_new_effect(scope, scope_key_set, name, level, options)
        self._notify_listeners(f"{name}.start", scope_key_set, scope, receipt)
        return receipt

    def stop_effect_by_receipt(self, receipt: EffectReceipt) -> None:
        """Stop the single effect identified by receipt; silent no-op if not found."""
        new_effects = []
        for entry in self._effects:
            if entry.receipt is receipt:
                self._notify_listeners(
                    f"{entry.name}.stop", set(entry.keys), entry.scope, entry.receipt
                )
            else:
                new_effects.append(entry)
        self._effects = new_effects

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        self._remove_effects_in_scope(set(scope.keys))

    def update(self, timer: Timer) -> None:
        """Tick all active effects and deliver frames to every registered output."""
        self._timer.update(timer.elapsed)

        # Pass 1: advance each renderer once.
        for entry in self._effects:
            entry.renderer.update(entry.state, self._timer)

        # Pass 2: render and deliver to each output using pre-allocated buffers.
        # Outputs whose scopes have no active effects receive [] (go-dark signal).
        for i in range(len(self._outputs)):
            output = self._outputs[i]
            frames = self._frames[i]
            frames.clear()
            for entry in self._effects:
                buf = entry.output_buffers[i]
                if buf is not None:
                    entry.renderer.render(entry.state, buf)
                    frames.append((buf, entry.receipt))
            output.update_pixels(frames)

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
