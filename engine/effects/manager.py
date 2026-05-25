from effects.effect import EffectState, EffectTimer
from effects.render import EffectRenderer, PixelBuffer, RendererConfig
from engine.packs import PackRegistry
from engine.state import EffectControls, EffectReceipt, ScopeValue
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

    def create_buffer(self, scope_key: str) -> PixelBuffer:
        """Create a PixelBuffer sized for the given scope key's hardware region."""
        raise NotImplementedError

    def update_pixels(self, frames: list[tuple[PixelBuffer, EffectReceipt]]) -> None:
        """Receive rendered frames for this output.

        Called every update tick. Each element is a (PixelBuffer, EffectReceipt) tuple.
        Receives an empty list when no effects are active (signal to go dark).
        """
        pass

    def show_pixels(self) -> None:
        """Commit staged pixel data to hardware or other sinks.

        Called unconditionally once per tick, after ``update_pixels`` for this
        output. Concrete pixel outputs override this to flush their hardware
        buffer (e.g. ``strip.show()`` for NeoPixels). Audio and event outputs
        may leave this as a no-op.
        """
        pass

    def handle_event(
        self, event_name: str, scope_keys: frozenset[str], receipt: EffectReceipt
    ) -> None:
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
        __slots__ = ("keys", "name", "output_buffers", "receipt", "renderer", "state")

        def __init__(
            self,
            keys: tuple[str, ...],
            name: str,
            receipt: EffectReceipt,
            output_buffers: list[dict[str, PixelBuffer] | None],
            renderer: EffectRenderer | None,
            state: EffectState,
        ) -> None:
            self.keys: tuple[str, ...] = keys
            self.name: str = name
            self.receipt: EffectReceipt = receipt
            self.output_buffers: list[dict[str, PixelBuffer] | None] = output_buffers
            self.renderer: EffectRenderer | None = renderer
            self.state: EffectState = state

        def __repr__(self) -> str:
            return (
                f"_EffectEntry(name={self.name!r}, receipt_id={self.receipt.id},"
                f" keys={self.keys!r})"
            )

    __slots__ = (
        "_effects",
        "_frames",
        "_next_id",
        "_output_key_sets",
        "_outputs",
        "_registry",
        "_timer",
    )

    def __init__(self, registry: PackRegistry, outputs: list[EffectOutput]) -> None:
        self._registry: PackRegistry = registry
        self._outputs: list[EffectOutput] = outputs
        self._effects: list[EffectManager._EffectEntry] = []
        self._next_id: int = 1
        self._timer: EffectTimer = EffectTimer()
        self._output_key_sets: list[frozenset[str]] = [
            frozenset(k for s in o.scopes for k in s.keys) for o in outputs
        ]
        self._frames: list[list[tuple[PixelBuffer, EffectReceipt]]] = [[] for _ in outputs]

    def _notify_listeners(
        self, event_name: str, event_keys: set[str], receipt: EffectReceipt
    ) -> None:
        """Notify outputs whose registered key sets intersect event_keys."""
        for i in range(len(self._outputs)):
            matching = event_keys & self._output_key_sets[i]
            if matching:
                self._outputs[i].handle_event(event_name, frozenset(matching), receipt)

    def _build_effect(
        self,
        scope: ScopeValue,
        scope_key_set: set[str],
        name: str,
        level: int,
        options: dict[str, object],
    ) -> "EffectManager._EffectEntry":
        """Construct an EffectRenderer paired with a fresh EffectState.

        *name* must be in ``"pack.effect"`` format.  The pack portion is used to
        look up the registered pack in the ``PackRegistry``; the bare effect name
        is passed to that pack's builder.
        """
        if "." not in name:
            raise ValueError(f"Effect name '{name}' missing pack prefix (expected 'pack.effect')")
        pack_name, effect_name = name.split(".", 1)
        try:
            builder = self._registry.get(pack_name, effect_name, EffectBuilder)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("Unknown pack '"):
                raise ValueError(f"Unknown effect pack '{pack_name}'") from exc
            if msg.startswith("Unknown item '"):
                raise ValueError(f"Unknown effect '{effect_name}' in pack '{pack_name}'") from exc
            if "is not an instance of" in msg:
                raise ValueError(
                    f"Effect '{effect_name}' in pack '{pack_name}' has an invalid BUILD attribute"
                ) from exc
            if msg.startswith("Pack '"):
                raise ValueError(
                    f"Effect pack '{pack_name}' item '{effect_name}' is missing a BUILD attribute"
                ) from exc
            raise

        receipt = EffectReceipt(self._next_id)
        self._next_id += 1

        resolution = _DEFAULT_RESOLUTION
        output_buffers = []
        for i, output in enumerate(self._outputs):
            matching_keys = scope_key_set & self._output_key_sets[i]
            if matching_keys:
                if output.min_resolution > resolution:
                    resolution = output.min_resolution
                output_buffers.append({k: output.create_buffer(k) for k in matching_keys})
            else:
                output_buffers.append(None)

        entry = EffectManager._EffectEntry(
            scope.keys, effect_name, receipt, output_buffers, None, EffectState()
        )

        def scoped_listener(event_name: str) -> None:
            self._notify_listeners(event_name, set(entry.keys), receipt)

        config = RendererConfig(
            level=level, resolution=resolution, options=options, listeners=[scoped_listener]
        )
        entry.renderer = builder(effect_name, config)
        return entry

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
        """Remove keys no longer in entry.keys from per-output buffer dicts."""
        key_set = set(entry.keys)
        for i in range(len(self._outputs)):
            buf_dict = entry.output_buffers[i]
            if buf_dict is None:
                continue
            for k in list(buf_dict):
                if k not in key_set:
                    del buf_dict[k]
            if not buf_dict:
                entry.output_buffers[i] = None

    def _remove_effects_in_scope(self, scope_key_set: set[str]) -> None:
        """Remove or narrow entries that overlap scope_key_set, firing stop events."""
        new_effects = []
        for entry in self._effects:
            remaining = tuple(k for k in entry.keys if k not in scope_key_set)
            if len(remaining) < len(entry.keys):
                self._notify_listeners(f"{entry.name}.stop", scope_key_set, entry.receipt)
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
        effect_name = name.split(".", 1)[1]
        self._notify_listeners(f"{effect_name}.start", scope_key_set, receipt)
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
        effect_name = name.split(".", 1)[1]
        self._notify_listeners(f"{effect_name}.start", scope_key_set, receipt)
        return receipt

    def stop_effect_by_receipt(self, receipt: EffectReceipt) -> None:
        """Stop the single effect identified by receipt; silent no-op if not found."""
        new_effects = []
        for entry in self._effects:
            if entry.receipt is receipt:
                self._notify_listeners(f"{entry.name}.stop", set(entry.keys), entry.receipt)
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
                buf_dict = entry.output_buffers[i]
                if buf_dict is not None:
                    for buf in buf_dict.values():
                        entry.renderer.render(entry.state, buf)
                        frames.append((buf, entry.receipt))
            output.update_pixels(frames)
            output.show_pixels()

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
