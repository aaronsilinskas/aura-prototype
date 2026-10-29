from __future__ import annotations

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

from effects.effect import Effect, EffectConfig, PixelBuffer, ResolvedClip
from engine.effects.merge import SPLIT
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.state import EffectAdmin, EffectControls, EffectReceipt, MergeStrategy, ScopeValue
from engine.timer import Timer

if TYPE_CHECKING:
    # Type-only: engine.namespace imports EffectBuilder from this module.
    from engine.namespace import ActiveSceneNamespace

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


class EffectManager(EffectControls, EffectAdmin):
    """Manages running effects and routes rendered frames to registered outputs each tick.

    Update model:
      - Call ``update(timer)`` once per frame. Each unique effect is
        advanced exactly once; outputs receive their frames in a second pass.
      - Each registered key gets either one ``update_pixels`` call with a
        single composed buffer, or a ``clear_pixels`` call when no effects
        are active for that key (go-dark signal).
    State ownership:
      - Output buffers are created once per effect via ``EffectOutput.create_buffer``.
    """

    class _EffectEntry:
        __slots__ = ("clips", "effect", "keys", "name", "output_buffers", "receipt")

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
            # Verb → Resolved clip, owned by this running effect. Never written
            # back onto the effect's shared AudioPlaybackConfig declarations.
            self.clips: dict[str, ResolvedClip] = {}

        def __repr__(self) -> str:
            rid = self.receipt.id
            return f"_EffectEntry(name={self.name!r}, receipt_id={rid}, keys={self.keys!r})"

    __slots__ = (
        "_effects",
        "_frame_bufs",
        "_frame_effects",
        "_frame_receipts",
        "_merge_strategies",
        "_namespace",
        "_next_id",
        "_output_key_sets",
        "_outputs",
    )

    def __init__(self, namespace: ActiveSceneNamespace, outputs: list[EffectOutput]) -> None:
        self._namespace: ActiveSceneNamespace = namespace
        self._outputs: list[EffectOutput] = outputs
        self._effects: list[EffectManager._EffectEntry] = []
        self._next_id: int = 1
        self._output_key_sets: list[frozenset[str]] = [
            frozenset(k for s in o.scopes for k in s.keys) for o in outputs
        ]
        # Every registered scope key defaults to the Split merge strategy.
        self._merge_strategies: dict[str, MergeStrategy] = {
            k: SPLIT for key_set in self._output_key_sets for k in key_set
        }
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
        self._frame_effects: list[dict[str, list[Effect]] | None] = [
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
    ) -> EffectManager._EffectEntry:
        """Construct an Effect for the named effect and resolve every clip it declares.

        Every verb's clip is resolved now, not when the verb first fires, so
        a misspelled clip on a rarely fired verb fails here too. Nothing is
        cached: each build resolves afresh against the active scene.

        Raises:
            RegistryError: the effect name, or one of the built effect's clip
                names, does not resolve in the active scene namespace (see
                ``ActiveSceneNamespace.resolve_effect`` and ``resolve_clip``).
        """
        builder, pack_name, effect_name = self._namespace.resolve_effect(name)

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
                EffectEvent(pack_name, effect_name, event_name, entry.clips.get(event_name)),
                set(entry.keys),
                entry.effect,
                receipt,
            )

        config = EffectConfig(resolution=resolution, options=options, listeners=[scoped_listener])
        entry.effect = builder(effect_name, config)

        audio = entry.effect.audio
        if audio is not None:
            for verb, clip_config in audio.clips.items():
                path = self._namespace.resolve_clip(clip_config.name)
                entry.clips[verb] = ResolvedClip(clip_config, path)

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

    def _update_output_buffers(self, entry: EffectManager._EffectEntry) -> None:
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
        stopped: list[tuple[EffectManager._EffectEntry, set[str]]],
        remaining: list[EffectManager._EffectEntry],
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
                EffectEvent(pack_name, effect_name, "stop", entry.clips.get("stop")),
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

    def set_merge_strategy(self, scope: ScopeValue, strategy: MergeStrategy) -> None:
        """Set the merge strategy for every key in scope.keys.

        Keys outside scope.keys are left unchanged. Takes effect starting with
        the next tick's ``prepare_buffers`` call.
        """
        for key in scope.keys:
            self._merge_strategies[key] = strategy

    def reset_merge_strategies(self) -> None:
        """Reset every registered scope key's merge strategy to SPLIT.

        Reserved for ``SceneManager`` (via the ``EffectAdmin`` face) — called
        from ``_do_load`` so no strategy choice survives a ``load``.
        """
        for key in self._merge_strategies:
            self._merge_strategies[key] = SPLIT

    def capture_merge_strategies(self) -> dict[str, MergeStrategy]:
        """Return an independent copy of the current per-scope merge strategy map.

        The live map is left in place, so an overlay starts by inheriting the
        underlying scene's current choices while remaining free to change
        them. Reserved for ``SceneManager`` (via the ``EffectAdmin`` face) —
        called from ``_do_overlay``; the returned copy rides in the scene
        stack entry the overlay pushes.
        """
        return dict(self._merge_strategies)

    def apply_merge_strategies(self, snapshot: dict[str, MergeStrategy]) -> None:
        """Direct-install *snapshot* as the live per-scope merge strategy map.

        *snapshot* is installed by reference, not copied: ``capture_merge_strategies``
        already unaliased it from the live map at capture time, and the caller
        discards the scene stack entry that owned it immediately after this
        call, so there is no reuse to protect against. Reserved for
        ``SceneManager`` (via the ``EffectAdmin`` face) — called from
        ``_do_pop`` with the popped entry's saved snapshot.
        """
        self._merge_strategies = snapshot

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Replace any running effect(s) in scope and start this one.

        The new effect is built before anything in scope is stopped, so a
        name that fails to resolve raises with the scope left as it was.
        """
        scope_key_set = set(scope.keys)
        entry = self._build_effect(scope_key_set, name, options)
        self._remove_effects_in_scope(scope_key_set)
        self._effects.append(entry)
        pack_name, effect_name = name.split(".", 1)
        self._notify_listeners(
            EffectEvent(pack_name, effect_name, "start", entry.clips.get("start")),
            scope_key_set,
            entry.effect,
            entry.receipt,
        )
        return entry.receipt

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        scope_key_set = set(scope.keys)
        entry = self._build_effect(scope_key_set, name, options)
        self._effects.append(entry)
        pack_name, effect_name = name.split(".", 1)
        self._notify_listeners(
            EffectEvent(pack_name, effect_name, "start", entry.clips.get("start")),
            scope_key_set,
            entry.effect,
            entry.receipt,
        )
        return entry.receipt

    def stop_effect(self, scope: ScopeValue) -> None:
        """Stop all running effects in scope."""
        self._remove_effects_in_scope(set(scope.keys))

    def update(self, timer: Timer) -> None:
        """Tick all active effects and deliver frames to every registered output."""
        # Deferred-stop: remove any effects whose receipt was marked stopped since
        # the last tick.  This runs before Pass 1 so that stop events and
        # clear_pixels fire before the new frame is rendered, and so that calling
        # receipt.stop() from within output.flush() during Pass 2 is safe.
        # The detection scan is allocation-free; the partition lists are built
        # only when something actually stopped, so the steady-state tick (nothing
        # stopping) never allocates here.
        any_stopped = False
        for entry in self._effects:
            if entry.receipt.is_stopped():
                any_stopped = True
                break
        if any_stopped:
            stopped: list[tuple[EffectManager._EffectEntry, set[str]]] = []
            new_effects: list[EffectManager._EffectEntry] = []
            for entry in self._effects:
                if entry.receipt.is_stopped():
                    stopped.append((entry, set(entry.keys)))
                else:
                    new_effects.append(entry)
            self._stop_entries(stopped, new_effects)
            self._effects = new_effects

        elapsed = timer.elapsed

        # Pass 1: advance each effect once.
        for entry in self._effects:
            if entry.effect.pixels is not None:
                entry.effect.pixels.update(elapsed)

        # Pass 2: merge and deliver one composed frame per key to each output.
        # Render must happen between prepare_buffers and merge — each buffer
        # is only correctly sized (by the key's MergeStrategy) once
        # prepare_buffers has run, and merge reads the rendered pixels.
        # _frame_bufs, _frame_receipts, and _frame_effects are pre-allocated in
        # __init__ and cleared here — no new objects in steady state after warmup.
        # Non-pixel outputs (receives_pixels=False) skip update_pixels entirely;
        # flush() is always called unconditionally.
        for i, output in enumerate(self._outputs):
            if output.receives_pixels:
                frame_bufs = self._frame_bufs[i]
                frame_receipts = self._frame_receipts[i]
                frame_effects = self._frame_effects[i]
                for buf_list in frame_bufs.values():
                    buf_list.clear()
                for receipt_list in frame_receipts.values():
                    receipt_list.clear()
                for effect_list in frame_effects.values():
                    effect_list.clear()
                for entry in self._effects:
                    buf_dict = entry.output_buffers[i]
                    if buf_dict is not None:
                        for k, buf in buf_dict.items():
                            frame_bufs[k].append(buf)
                            frame_receipts[k].append(entry.receipt)
                            frame_effects[k].append(entry.effect)
                for key, bufs in frame_bufs.items():
                    if not bufs:
                        output.clear_pixels(key)
                        continue
                    strategy = self._merge_strategies[key]
                    strategy.prepare_buffers(bufs)
                    effects = frame_effects[key]
                    for j, buf in enumerate(bufs):
                        effects[j].pixels.render(buf)
                    composed = strategy.merge(bufs, frame_receipts[key])
                    output.update_pixels(key, composed)
            output.flush()

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
