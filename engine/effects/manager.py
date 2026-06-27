from effects.effect import Effect, EffectConfig, PixelBuffer
from engine.events import EffectEvent
from engine.packs import PackRegistry
from engine.scene import SceneLocalRegistry
from engine.state import EffectControls, EffectReceipt, ScopeValue
from engine.timer import Timer

_DEFAULT_RESOLUTION = 16


class EffectBuilder:
    """Factory interface for constructing ``Effect`` instances by name.

    Concrete implementations look up the named effect and return an effect
    configured for the given ``EffectConfig``. Raise ``KeyError`` or
    ``ValueError`` for unregistered names.
    """

    def __call__(self, name: str, config: EffectConfig) -> Effect:
        """Build an Effect for the named effect.

        Args:
            name: The registered effect name (e.g. ``"color.flash"``).
            config: Runtime configuration for the render pass. ``config.get_option``
                carries any effect-specific parameters (e.g. duration, color).
                ``config.resolution`` describes the output hardware.

        Returns:
            A configured ``Effect`` ready to be advanced each frame.
        """
        raise NotImplementedError


class EffectResolver:
    """Maps a qualified effect name to an (builder, pack_name, effect_name) tuple.

    Owns the ``scene.`` reserved-prefix rule, the choice of registry for each
    name, and the translation of registry ``ValueError``\\s into effect-facing
    messages.  ``EffectManager`` holds one resolver and calls ``resolve`` once
    per effect start.

    CircuitPython/MicroPython safe: no per-call allocations beyond what the
    underlying registries already do; ``__slots__`` prevents ``__dict__``.
    """

    __slots__ = ("_local_effects", "_registry")

    def __init__(self, registry: PackRegistry) -> None:
        self._registry: PackRegistry = registry
        self._local_effects: SceneLocalRegistry | None = None

    def set_local_effects(self, local_registry: SceneLocalRegistry | None) -> None:
        """Replace the active scene-local registry.  Pass ``None`` to clear."""
        self._local_effects = local_registry

    def resolve(self, name: str) -> tuple[EffectBuilder, str, str]:
        """Return ``(builder, pack_name, effect_name)`` for *name*.

        *name* must be in ``"pack.effect"`` or ``"scene.effect"`` format.
        The ``scene.`` prefix routes to the currently-active scene-local
        registry.  All other prefixes route to the shared ``PackRegistry``.

        Raises:
            ValueError: for any resolution failure, with an effect-facing
                message (missing prefix, unknown pack, unknown effect,
                invalid/missing ``BUILD``, ``scene.`` with no active scene,
                unknown scene-local effect).
        """
        if "." not in name:
            raise ValueError(
                "Effect name '" + name + "' missing pack prefix (expected 'pack.effect')"
            )
        pack_name, effect_name = name.split(".", 1)

        if pack_name == "scene":
            builder = self._resolve_scene(name, effect_name)
        else:
            builder = self._resolve_pack(pack_name, effect_name)

        return builder, pack_name, effect_name

    def _resolve_scene(self, name: str, effect_name: str) -> EffectBuilder:
        if self._local_effects is None:
            raise ValueError(
                "Effect name '"
                + name
                + "' uses the reserved 'scene.' prefix but no scene is active"
            )
        try:
            return self._local_effects.get(effect_name, EffectBuilder)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("Unknown item '"):
                raise ValueError(
                    "Unknown scene-local effect '"
                    + effect_name
                    + "'. Available: "
                    + ", ".join(self._local_effects.items())
                ) from exc
            raise

    def _resolve_pack(self, pack_name: str, effect_name: str) -> EffectBuilder:
        try:
            return self._registry.get(pack_name, effect_name, EffectBuilder)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("Unknown pack '"):
                raise ValueError("Unknown effect pack '" + pack_name + "'") from exc
            if msg.startswith("Unknown item '"):
                raise ValueError(
                    "Unknown effect '" + effect_name + "' in pack '" + pack_name + "'"
                ) from exc
            if "is not an instance of" in msg:
                raise ValueError(
                    "Effect '" + effect_name + "' in pack '" + pack_name + "'"
                    " has an invalid BUILD attribute"
                ) from exc
            if msg.startswith("Pack '"):
                raise ValueError(
                    "Effect pack '" + pack_name + "' item '" + effect_name + "'"
                    " is missing a BUILD attribute"
                ) from exc
            raise


class EffectOutput:
    """Interface for sending rendered pixels and events to hardware outputs.

    Concrete subclasses must set in their __init__:
      - min_resolution: int  — minimum pixel count needed by this output.
      - scopes: list         — list of ScopeValue this output serves.
    """

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

    def update_pixels(
        self, scope_key: str, buffers: list[PixelBuffer], receipts: list[EffectReceipt]
    ) -> None:
        """Receive rendered frames for this output for a single scope key.

        Called once per registered scope key per tick. ``buffers`` and
        ``receipts`` are parallel lists ordered by effect start time (oldest
        first). Both are empty when no effects are active for that key
        (go-dark signal).
        """
        pass

    def flush(self) -> None:
        """Commit staged pixel data to hardware or other sinks.

        Called unconditionally once per tick, after ``update_pixels`` for this
        output. Concrete pixel outputs override this to flush their hardware
        buffer (e.g. ``strip.show()`` for NeoPixels). Audio and event outputs
        may leave this as a no-op.
        """
        pass

    def clear_pixels(self, scope_key: str) -> None:
        """Signal that the given scope key should go dark.

        Called when the last effect covering this key stops. Hardware outputs
        can override this to explicitly clear their buffer (e.g. write zeros to
        LEDs). Default is a no-op.
        """
        pass

    def handle_event(
        self, event: EffectEvent, scope_keys: frozenset[str], effect: Effect, receipt: EffectReceipt
    ) -> None:
        """Handle an event triggered by an effect lifecycle or effect-triggered signal.

        Lifecycle events (start/stop) and effect-triggered signals all deliver
        an ``EffectEvent`` instance.
        """
        pass


class EffectManager(EffectControls):
    """Manages running effects and routes rendered frames to registered outputs each tick.

    Update model:
      - Call ``update(timer)`` once per frame. Each unique effect is
        advanced exactly once; outputs receive their frames in a second pass.
      - Outputs always receive a call, with an empty list when no effects
        are active (go-dark signal).
    State ownership:
      - Output buffers are created once per effect via ``EffectOutput.create_buffer``.
    """

    class _EffectEntry:
        __slots__ = ("effect", "keys", "name", "output_buffers", "receipt")

        def __init__(
            self,
            keys: tuple[str, ...],
            name: str,
            receipt: EffectReceipt,
            output_buffers: list[dict[str, PixelBuffer] | None],
            effect: Effect | None,
        ) -> None:
            self.keys: tuple[str, ...] = keys
            self.name: str = name
            self.receipt: EffectReceipt = receipt
            self.output_buffers: list[dict[str, PixelBuffer] | None] = output_buffers
            self.effect: Effect | None = effect

        def __repr__(self) -> str:
            return (
                f"_EffectEntry(name={self.name!r}, receipt_id={self.receipt.id},"
                f" keys={self.keys!r})"
            )

    __slots__ = (
        "_effects",
        "_frame_bufs",
        "_frame_receipts",
        "_next_id",
        "_output_key_sets",
        "_outputs",
        "_resolver",
    )

    def __init__(self, registry: PackRegistry, outputs: list[EffectOutput]) -> None:
        self._resolver: EffectResolver = EffectResolver(registry)
        self._outputs: list[EffectOutput] = outputs
        self._effects: list[EffectManager._EffectEntry] = []
        self._next_id: int = 1
        self._output_key_sets: list[frozenset[str]] = [
            frozenset(k for s in o.scopes for k in s.keys) for o in outputs
        ]
        # Pre-allocated per-output frame accumulators — cleared and reused each tick
        # to avoid dict/list allocation in the hot path.
        # Non-pixel outputs (receives_pixels=False) use None as a placeholder.
        self._frame_bufs: list[dict[str, list[PixelBuffer]] | None] = [
            {k: [] for k in key_set} if o.receives_pixels else None
            for o, key_set in zip(outputs, self._output_key_sets)
        ]
        self._frame_receipts: list[dict[str, list[EffectReceipt]] | None] = [
            {k: [] for k in key_set} if o.receives_pixels else None
            for o, key_set in zip(outputs, self._output_key_sets)
        ]

    def _notify_listeners(
        self,
        event: EffectEvent,
        event_keys: set[str],
        effect: Effect | None,
        receipt: EffectReceipt,
    ) -> None:
        """Notify outputs whose registered key sets intersect event_keys."""
        for i in range(len(self._outputs)):
            matching = event_keys & self._output_key_sets[i]
            if matching:
                self._outputs[i].handle_event(event, frozenset(matching), effect, receipt)

    def _build_effect(
        self,
        scope_key_set: set[str],
        name: str,
        options: dict[str, object],
    ) -> "EffectManager._EffectEntry":
        """Construct an Effect for the named effect."""
        builder, pack_name, effect_name = self._resolver.resolve(name)

        receipt = EffectReceipt(self._next_id)
        self._next_id += 1
        receipt.brightness = float(options.get("brightness", 1.0))
        receipt.loudness = float(options.get("loudness", 1.0))

        resolution = _DEFAULT_RESOLUTION
        for i, output in enumerate(self._outputs):
            matching_keys = scope_key_set & self._output_key_sets[i]
            if matching_keys and output.min_resolution > resolution:
                resolution = output.min_resolution

        entry = EffectManager._EffectEntry(tuple(scope_key_set), name, receipt, [], None)

        def scoped_listener(event_name: str) -> None:
            self._notify_listeners(
                EffectEvent(pack_name, effect_name, event_name),
                set(entry.keys),
                entry.effect,
                receipt,
            )

        config = EffectConfig(resolution=resolution, options=options, listeners=[scoped_listener])
        entry.effect = builder(effect_name, config)

        if entry.effect.pixels is not None:
            for i, output in enumerate(self._outputs):
                matching_keys = scope_key_set & self._output_key_sets[i]
                if matching_keys and output.receives_pixels:
                    entry.output_buffers.append({k: output.create_buffer(k) for k in matching_keys})
                else:
                    entry.output_buffers.append(None)
        else:
            entry.output_buffers = [None] * len(self._outputs)

        return entry

    def _append_new_effect(
        self,
        scope: ScopeValue,
        scope_key_set: set[str],
        name: str,
        options: dict[str, object],
    ) -> "EffectManager._EffectEntry":
        """Build, append, and return the new effect entry."""
        entry = self._build_effect(scope_key_set, name, options)
        self._effects.append(entry)
        return entry

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

    def _stop_entries(
        self,
        stopped: "list[tuple[EffectManager._EffectEntry, set[str]]]",
        remaining: "list[EffectManager._EffectEntry]",
    ) -> None:
        """Fire stop events and clear_pixels for entries that have stopped or been narrowed.

        Args:
            stopped: List of ``(entry, removed_keys)`` pairs. ``removed_keys`` is the set
                of scope keys being removed from each entry (used for event routing).
            remaining: The effects that will remain active after this stop operation,
                with their keys already narrowed to the post-stop state.
        """
        for entry, removed_keys in stopped:
            pack_name, effect_name = entry.name.split(".", 1)
            self._notify_listeners(
                EffectEvent(pack_name, effect_name, "stop"),
                removed_keys,
                entry.effect,
                entry.receipt,
            )

        remaining_key_set: set[str] = set()
        for r in remaining:
            remaining_key_set.update(r.keys)

        checked: set[str] = set()
        for _, removed_keys in stopped:
            for key in removed_keys:
                if key in checked:
                    continue
                checked.add(key)
                if key not in remaining_key_set:
                    for i in range(len(self._outputs)):
                        if key in self._output_key_sets[i]:
                            self._outputs[i].clear_pixels(key)

    def _remove_effects_in_scope(self, scope_key_set: set[str]) -> None:
        """Remove or narrow entries that overlap scope_key_set, firing stop events."""
        stopped: list[tuple[EffectManager._EffectEntry, set[str]]] = []
        new_effects: list[EffectManager._EffectEntry] = []
        for entry in self._effects:
            remaining = tuple(k for k in entry.keys if k not in scope_key_set)
            if len(remaining) < len(entry.keys):
                stopped.append((entry, scope_key_set))
            if remaining:
                entry.keys = remaining
                self._update_output_buffers(entry)
                new_effects.append(entry)
        self._stop_entries(stopped, new_effects)
        self._effects = new_effects

    def set_local_effects(self, local_registry: SceneLocalRegistry | None) -> None:
        """Store the active scene's local effect registry.

        Called by ``SceneManager`` at each scene transition so that
        ``scene.<effect>`` names resolve against the top-of-stack scene's
        local effects.  Pass ``None`` when the stack empties.

        Reserved for ``SceneManager`` — rules must not call this method.
        """
        self._resolver.set_local_effects(local_registry)

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Replace any running effect(s) in scope and start this one."""
        scope_key_set = set(scope.keys)
        self._remove_effects_in_scope(scope_key_set)
        entry = self._append_new_effect(scope, scope_key_set, name, options)
        pack_name, effect_name = name.split(".", 1)
        self._notify_listeners(
            EffectEvent(pack_name, effect_name, "start"), scope_key_set, entry.effect, entry.receipt
        )
        return entry.receipt

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        scope_key_set = set(scope.keys)
        entry = self._append_new_effect(scope, scope_key_set, name, options)
        pack_name, effect_name = name.split(".", 1)
        self._notify_listeners(
            EffectEvent(pack_name, effect_name, "start"), scope_key_set, entry.effect, entry.receipt
        )
        return entry.receipt

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        self._remove_effects_in_scope(set(scope.keys))

    def warm_effect(self, name: str) -> None:
        """Import and cache *name*'s builder without building an effect or buffers.

        See ``EffectControls.warm_effect`` for why this runs at scene setup.
        """
        self._resolver.resolve(name)

    def update(self, timer: Timer) -> None:
        """Tick all active effects and deliver frames to every registered output."""
        # Deferred-stop: remove any effects whose receipt was marked stopped since
        # the last tick.  This runs before Pass 1 so that stop events and
        # clear_pixels fire before the new frame is rendered, and so that calling
        # receipt.stop() from within output.flush() during Pass 2 is safe.
        stopped: list[tuple[EffectManager._EffectEntry, set[str]]] = []
        new_effects: list[EffectManager._EffectEntry] = []
        for entry in self._effects:
            if entry.receipt.is_stopped():
                stopped.append((entry, set(entry.keys)))
            else:
                new_effects.append(entry)
        if stopped:
            self._stop_entries(stopped, new_effects)
            self._effects = new_effects

        elapsed = timer.elapsed

        # Pass 1: advance each effect once.
        for entry in self._effects:
            if entry.effect.pixels is not None:
                entry.effect.pixels.update(elapsed)

        # Pass 2: render and deliver per-key frames to each output.
        # Every registered key receives a call; empty lists signal go-dark.
        # _frame_bufs and _frame_receipts are pre-allocated in __init__ and cleared
        # here — no new objects in steady state after warmup.
        # Non-pixel outputs (receives_pixels=False) skip update_pixels entirely;
        # flush() is always called unconditionally.
        for i, output in enumerate(self._outputs):
            if output.receives_pixels:
                frame_bufs = self._frame_bufs[i]
                frame_receipts = self._frame_receipts[i]
                for buf_list in frame_bufs.values():
                    buf_list.clear()
                for receipt_list in frame_receipts.values():
                    receipt_list.clear()
                for entry in self._effects:
                    buf_dict = entry.output_buffers[i]
                    if buf_dict is not None:
                        for k, buf in buf_dict.items():
                            entry.effect.pixels.render(buf)
                            frame_bufs[k].append(buf)
                            frame_receipts[k].append(entry.receipt)
                for key in frame_bufs:
                    output.update_pixels(key, frame_bufs[key], frame_receipts[key])
            output.flush()

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
