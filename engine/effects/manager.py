from __future__ import annotations

from effects.effect import (
    Effect,
    EffectConfig,
    EffectPixels,
    EffectVerb,
    PixelBuffer,
    ResolvedClip,
)
from engine.effects.admin import EffectAdmin, HeldEffects
from engine.effects.merge import SPLIT
from engine.effects.output import EffectOutput
from engine.events import EffectEvent
from engine.namespace import ActiveSceneNamespace
from engine.state import (
    EffectControls,
    EffectReceipt,
    MergeStrategy,
    ScopeValue,
)
from engine.timer import Timer

TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

_DEFAULT_RESOLUTION = 16


class VerbKeyError(ValueError):
    """A built effect keys ``clips`` or ``patterns`` on a verb it cannot use there.

    Raised by ``EffectManager.set_effect``/``add_effect`` before anything in
    scope is stopped. Not a **Registry lookup error**: every name resolved, but
    the key is not one of the verbs the effect can emit (``Effect.emitted_verbs``),
    or it is a ``STOP`` clip. *effect_name* is qualified, *modality* is
    ``"clips"`` or ``"patterns"``, *problem* says what is wrong with *verb*,
    and *emitted* lists the verbs the effect can emit.
    """

    def __init__(
        self,
        effect_name: str,
        modality: str,
        verb: EffectVerb,
        problem: str,
        emitted: tuple[EffectVerb, ...],
    ) -> None:
        self.effect_name = effect_name
        self.modality = modality
        self.verb = verb
        self.emitted = emitted
        super().__init__(
            f"Effect '{effect_name}' {modality} key {verb!r} {problem} "
            + f"(it emits {', '.join(repr(v) for v in emitted)})"
        )


def _reject_unemitted_verbs(
    effect_name: str,
    modality: str,
    keys: Iterable[EffectVerb],
    emitted: tuple[EffectVerb, ...],
) -> None:
    """Raise ``VerbKeyError`` for the first of *keys* not in *emitted*, matched by identity."""
    for verb in keys:
        if not any(verb is known for known in emitted):
            raise VerbKeyError(effect_name, modality, verb, "is not a verb it emits", emitted)


def _float_option(options: dict[str, object], key: str) -> float:
    """Return ``options[key]`` as a float, 1.0 when absent; ``float()`` raises on the rest."""
    # Any, not object: float() alone decides what converts and what it raises.
    value: Any = options.get(key, 1.0)
    return float(value)


def _reject_stop_clip(
    effect_name: str, clips: Iterable[EffectVerb], emitted: tuple[EffectVerb, ...]
) -> None:
    """Raise ``VerbKeyError`` if *clips* keys a clip on ``EffectVerb.STOP``."""
    for verb in clips:
        if verb is EffectVerb.STOP:
            raise VerbKeyError(
                effect_name,
                "clips",
                verb,
                "cannot hold a clip: audio teardown is the output's flush(), not a "
                + "clip, so a STOP clip is cut off or plays only depending on how the "
                + "effect was stopped",
                emitted,
            )


class _HeldEffects(HeldEffects):
    """``EffectManager``'s held bundle: the set-aside effect entries and merge strategies."""

    __slots__ = ("effects", "merge_strategies")

    def __init__(
        self,
        effects: list[EffectManager._EffectEntry],
        merge_strategies: dict[str, MergeStrategy],
    ) -> None:
        self.effects = effects
        self.merge_strategies = merge_strategies


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
        __slots__ = (
            "clips",
            "effect",
            "effect_name",
            "keys",
            "output_buffers",
            "pack_name",
            "receipt",
        )

        def __init__(
            self,
            keys: tuple[str, ...],
            pack_name: str,
            effect_name: str,
            receipt: EffectReceipt,
            output_buffers: list[dict[str, PixelBuffer] | None],
        ) -> None:
            self.keys: tuple[str, ...] = keys
            self.pack_name: str = pack_name
            self.effect_name: str = effect_name
            self.receipt: EffectReceipt = receipt
            self.output_buffers: list[dict[str, PixelBuffer] | None] = output_buffers
            # Assigned by _build_effect once the builder returns: the effect's
            # listener closes over this entry, so the entry exists first.
            # Unset during the build is safe because effects announce verbs only
            # from update() (see EffectPixels), never while being built.
            self.effect: Effect
            # Verb → Resolved clip, owned by this running effect. Never written
            # back onto the effect's shared AudioPlaybackConfig declarations.
            self.clips: dict[EffectVerb, ResolvedClip] = {}

        def __repr__(self) -> str:
            rid = self.receipt.id
            name = self.pack_name + "." + self.effect_name
            return f"_EffectEntry(name={name!r}, receipt_id={rid}, keys={self.keys!r})"

    __slots__ = (
        "_effects",
        "_frame_bufs",
        "_frame_pixels",
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
        # Non-pixel outputs (receives_pixels=False) get an empty, unused placeholder.
        self._frame_bufs: list[dict[str, list[PixelBuffer]]] = [
            {k: [] for k in key_set} if o.receives_pixels else {}
            for o, key_set in zip(outputs, self._output_key_sets)
        ]
        self._frame_receipts: list[dict[str, list[EffectReceipt | None]]] = [
            {k: [] for k in key_set} if o.receives_pixels else {}
            for o, key_set in zip(outputs, self._output_key_sets)
        ]
        self._frame_pixels: list[dict[str, list[EffectPixels]]] = [
            {k: [] for k in key_set} if o.receives_pixels else {}
            for o, key_set in zip(outputs, self._output_key_sets)
        ]

    def _emit(
        self, entry: EffectManager._EffectEntry, verb: EffectVerb, event_keys: set[str]
    ) -> None:
        """Send *entry*'s *verb* event, with its resolved clip, to outputs serving event_keys."""
        event = EffectEvent(entry.pack_name, entry.effect_name, verb, entry.clips.get(verb))
        for i in range(len(self._outputs)):
            matching = event_keys & self._output_key_sets[i]
            if matching:
                self._outputs[i].handle_event(
                    event, frozenset(matching), entry.effect, entry.receipt
                )

    def _build_effect(
        self,
        scope_key_set: set[str],
        name: str,
        options: dict[str, object],
    ) -> EffectManager._EffectEntry:
        """Construct an Effect for the named effect, check its verb keys, and resolve its clips.

        Every verb's clip is resolved now, not when the verb first fires, so
        a misspelled clip on a rarely fired verb fails here too. Nothing is
        cached: each build resolves afresh against the active scene.

        Raises:
            RegistryError: the effect name, or one of the built effect's clip
                names, does not resolve in the active scene namespace (see
                ``ActiveSceneNamespace.resolve_effect`` and ``resolve_clip``).
            VerbKeyError: a ``clips`` or ``patterns`` key is not a verb the
                effect emits, or a ``clips`` key is ``EffectVerb.STOP``.
        """
        builder, pack_name, effect_name = self._namespace.resolve_effect(name)

        receipt = EffectReceipt(self._next_id)
        self._next_id += 1
        receipt.brightness = _float_option(options, "brightness")
        receipt.loudness = _float_option(options, "loudness")

        resolution = _DEFAULT_RESOLUTION
        for i, output in enumerate(self._outputs):
            matching_keys = scope_key_set & self._output_key_sets[i]
            if matching_keys and output.min_resolution > resolution:
                resolution = output.min_resolution

        entry = EffectManager._EffectEntry(
            tuple(scope_key_set), pack_name, effect_name, receipt, []
        )

        def scoped_listener(verb: EffectVerb) -> None:
            self._emit(entry, verb, set(entry.keys))

        config = EffectConfig(resolution=resolution, options=options, listeners=[scoped_listener])
        entry.effect = builder(effect_name, config)

        qualified = pack_name + "." + effect_name
        haptic = entry.effect.haptic
        audio = entry.effect.audio
        emitted = entry.effect.emitted_verbs()
        if haptic is not None:
            _reject_unemitted_verbs(qualified, "patterns", haptic.patterns, emitted)
        if audio is not None:
            _reject_unemitted_verbs(qualified, "clips", audio.clips, emitted)
            _reject_stop_clip(qualified, audio.clips, emitted)
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
            self._emit(entry, EffectVerb.STOP, removed_keys)

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
        """Remove or narrow entries that overlap scope_key_set, firing stop events.

        A removed entry's receipt is stopped, so outputs tracking it (a looping
        voice, a haptic sequence) release it on their next flush. A narrowed
        entry is still running, so its receipt is left alone.
        """
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
            else:
                entry.receipt.stop()
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
        by ``activate_boot_scene`` so the boot scene starts on Split.
        """
        for key in self._merge_strategies:
            self._merge_strategies[key] = SPLIT

    def set_aside(self) -> HeldEffects:
        """Move the running effects and merge strategies into a held bundle; restart on Split.

        No stop event fires. Each output is told which effects are held
        (``hold_effect``), so sound and haptics fall silent; pixel scopes
        simply have nothing to draw, so the next ``update`` clears them. See
        ``EffectAdmin.set_aside``.
        """
        for entry in self._effects:
            for output, keys in self._outputs_serving(entry):
                output.hold_effect(keys, entry.effect, entry.receipt)
        held = _HeldEffects(self._effects, self._merge_strategies)
        self._effects = []
        self._merge_strategies = dict.fromkeys(held.merge_strategies, SPLIT)
        return held

    def put_back(self, held: HeldEffects) -> None:
        """Install *held*'s effects and merge strategies as the live ones.

        Both are installed by reference: the bundle came from ``set_aside``,
        which already detached them, and the caller drops it right after.
        Each output is told which effects are restored (``restore_effect``).
        See ``EffectAdmin.put_back``.
        """
        assert isinstance(held, _HeldEffects)
        self._effects = held.effects
        self._merge_strategies = held.merge_strategies
        for entry in self._effects:
            for output, keys in self._outputs_serving(entry):
                output.restore_effect(keys, entry.effect, entry.receipt)

    def _outputs_serving(
        self, entry: EffectManager._EffectEntry
    ) -> list[tuple[EffectOutput, frozenset[str]]]:
        """Each output serving any of *entry*'s scope keys, with the keys it serves."""
        serving = []
        for i in range(len(self._outputs)):
            matching = self._output_key_sets[i].intersection(entry.keys)
            if matching:
                serving.append((self._outputs[i], matching))
        return serving

    def set_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Replace any running effect(s) in scope and start this one.

        The new effect is built before anything in scope is stopped, so a
        name that fails to resolve raises with the scope left as it was.
        """
        scope_key_set = set(scope.keys)
        entry = self._build_effect(scope_key_set, name, options)
        self._remove_effects_in_scope(scope_key_set)
        self._effects.append(entry)
        self._emit(entry, EffectVerb.START, scope_key_set)
        return entry.receipt

    def add_effect(self, scope: ScopeValue, name: str, options: dict[str, object]) -> EffectReceipt:
        """Layer this effect alongside any running effects in scope.

        If nothing is running in scope, behaves like set_effect.
        The driver determines how layered effects are composited (e.g. splitting an LED strip).
        """
        scope_key_set = set(scope.keys)
        entry = self._build_effect(scope_key_set, name, options)
        self._effects.append(entry)
        self._emit(entry, EffectVerb.START, scope_key_set)
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
        # _frame_bufs, _frame_receipts, and _frame_pixels are pre-allocated in
        # __init__ and cleared here — no new objects in steady state after warmup.
        # Non-pixel outputs (receives_pixels=False) skip update_pixels entirely;
        # flush() is always called unconditionally.
        for i, output in enumerate(self._outputs):
            if output.receives_pixels:
                frame_bufs = self._frame_bufs[i]
                frame_receipts = self._frame_receipts[i]
                frame_pixels = self._frame_pixels[i]
                for buf_list in frame_bufs.values():
                    buf_list.clear()
                for receipt_list in frame_receipts.values():
                    receipt_list.clear()
                for pixels_list in frame_pixels.values():
                    pixels_list.clear()
                for entry in self._effects:
                    buf_dict = entry.output_buffers[i]
                    # Buffers exist only when pixels do, so the pixels check never
                    # skips a buffer: it is there to narrow pixels for mypy.
                    pixels = entry.effect.pixels
                    if buf_dict is not None and pixels is not None:
                        for k, buf in buf_dict.items():
                            frame_bufs[k].append(buf)
                            frame_receipts[k].append(entry.receipt)
                            frame_pixels[k].append(pixels)
                for key, bufs in frame_bufs.items():
                    if not bufs:
                        output.clear_pixels(key)
                        continue
                    strategy = self._merge_strategies[key]
                    strategy.prepare_buffers(bufs)
                    key_pixels = frame_pixels[key]
                    for j, buf in enumerate(bufs):
                        key_pixels[j].render(buf)
                    composed = strategy.merge(bufs, frame_receipts[key])
                    output.update_pixels(key, composed)
            output.flush()

    def __repr__(self) -> str:
        if not self._effects:
            return "(no active effects)"
        return "\n".join(repr(entry) for entry in self._effects)
