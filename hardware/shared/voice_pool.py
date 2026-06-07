"""Hardware-agnostic audio voice-slot bookkeeping.

``VoicePool`` owns every voice-slot decision — slot occupancy, claim ordering,
the eviction policy, the audio-only receipt-stop rule, and loudness tracking —
without ever touching audio hardware.  All hardware lives behind the
``VoiceSink`` port, so the pool runs unchanged on CPython, CircuitPython, and
MicroPython and is testable with a plain recording fake.

Imports no CircuitPython modules (``audiobusio`` / ``audiocore`` /
``audiomixer`` / ``board``).
"""

from engine.state import EffectReceipt


class VoiceSink:
    """Port through which :class:`VoicePool` drives audio hardware.

    A plain base class (not ``typing.Protocol``, which is unavailable on the
    constrained runtimes).  The live adapter is ``AudioEffectOutput``; tests use
    a recording fake.  Loudness crosses this seam as a ``0..1`` value — the
    adapter owns the ``max_volume`` calibration.
    """

    def open_source(self, path: str) -> object | None:
        """Load the clip at ``path``; return an opaque source, or ``None`` on failure."""
        raise NotImplementedError

    def play(self, slot: int, source: object, loop: bool) -> None:
        """Store ``source`` and start playing it on ``slot``'s voice."""
        raise NotImplementedError

    def stop(self, slot: int) -> None:
        """Stop ``slot``'s voice and close its source — the single teardown path."""
        raise NotImplementedError

    def set_loudness(self, slot: int, loudness: float) -> None:
        """Apply a ``0..1`` loudness to ``slot``'s voice (calibration is internal)."""
        raise NotImplementedError

    def is_playing(self, slot: int) -> bool:
        """Return whether ``slot``'s voice is still playing."""
        raise NotImplementedError


class _Slot:
    """Mutable bookkeeping record for a single voice, allocated once and reused.

    One object per voice, mutated in place and never reallocated, so freeing a
    slot is a single-object reset rather than a lockstep update across parallel
    lists.
    """

    __slots__ = ("audio_only", "claim_seq", "is_loop", "loudness", "receipt")

    def __init__(self) -> None:
        self.receipt = None
        self.is_loop = False
        self.audio_only = False
        self.loudness = 1.0
        self.claim_seq = 0

    def reset(self) -> None:
        """Clear the slot back to idle (``receipt is None``)."""
        self.receipt = None
        self.is_loop = False
        self.audio_only = False
        self.loudness = 1.0
        self.claim_seq = 0


class VoicePool:
    """Owns voice-slot bookkeeping for a flat pool of ``num_voices`` voices.

    Any voice plays any clip.  ``claim`` selects a slot (first idle, else the
    eviction policy) and plays a clip; ``sweep`` reconciles slots each tick.
    All hardware is reached through an injected :class:`VoiceSink`.
    """

    __slots__ = ("_claim_counter", "_num_voices", "_slots")

    def __init__(self, num_voices: int) -> None:
        self._num_voices = num_voices
        self._slots = [_Slot() for _ in range(num_voices)]
        self._claim_counter = 0

    def _select_slot(self, loop: bool) -> int:
        """Return the slot to use for a new clip, or ``-1`` if none is claimable.

        Pure and side-effect-free.  Prefers the first idle slot.  Otherwise the
        eviction policy applies: a new loop evicts the oldest playing loop
        (fallback: the oldest slot overall); a new one-shot evicts the oldest
        playing one-shot (else ``-1``).  "Oldest" is the lowest ``claim_seq``.
        """
        preferred_slot = -1
        preferred_seq = -1
        fallback_slot = -1
        fallback_seq = -1

        for i in range(self._num_voices):
            s = self._slots[i]
            if s.receipt is None:
                return i
            seq = s.claim_seq
            if loop:
                if s.is_loop and (preferred_slot == -1 or seq < preferred_seq):
                    preferred_slot = i
                    preferred_seq = seq
                if fallback_slot == -1 or seq < fallback_seq:
                    fallback_slot = i
                    fallback_seq = seq
            else:
                if not s.is_loop and (preferred_slot == -1 or seq < preferred_seq):
                    preferred_slot = i
                    preferred_seq = seq

        if preferred_slot != -1:
            return preferred_slot
        if loop and fallback_slot != -1:
            return fallback_slot
        return -1

    def claim(
        self,
        sink: VoiceSink,
        path: str,
        loop: bool,
        audio_only: bool,
        receipt: EffectReceipt,
    ) -> int:
        """Play ``path`` on a claimed slot; return the slot, or ``-1`` if dropped.

        Selects the slot first (pure), then loads via ``sink.open_source``.  A
        slot pick of ``-1`` or a failed load evicts nothing — teardown is
        deferred until after a successful load.  When the evicted slot held an
        audio-only effect, its receipt is stopped (audio ending is the effect
        ending); non-audio-only receipts are left to rules.
        """
        slot = self._select_slot(loop)
        if slot == -1:
            return -1
        source = sink.open_source(path)
        if source is None:
            return -1
        s = self._slots[slot]
        if s.receipt is not None and s.audio_only:
            s.receipt.stop()
        sink.stop(slot)
        self._claim_counter += 1
        s.receipt = receipt
        s.is_loop = loop
        s.audio_only = audio_only
        s.loudness = receipt.loudness
        s.claim_seq = self._claim_counter
        sink.play(slot, source, loop)
        sink.set_loudness(slot, receipt.loudness)
        return slot

    def sweep(self, sink: VoiceSink) -> None:
        """Reconcile every slot once per tick.

        For each occupied slot: free a naturally-finished one-shot (stopping the
        receipt when audio-only), free an externally-stopped receipt (without
        stopping it again — rules already did), or reapply a changed loudness.
        ``range``-indexed to avoid per-tick tuple allocation.
        """
        for i in range(self._num_voices):
            s = self._slots[i]
            if s.receipt is None:
                continue
            if not s.is_loop and not sink.is_playing(i):
                audio_only = s.audio_only
                receipt = s.receipt
                sink.stop(i)
                s.reset()
                if audio_only:
                    receipt.stop()
                continue
            if s.receipt.is_stopped():
                sink.stop(i)
                s.reset()
                continue
            loudness = s.receipt.loudness
            if loudness != s.loudness:
                sink.set_loudness(i, loudness)
                s.loudness = loudness
