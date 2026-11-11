from __future__ import annotations

__all__ = [
    "EffectAdmin",
    "HeldEffects",
]


class HeldEffects:
    """A covered scene's running effects and merge strategies, set aside together.

    Returned by ``EffectAdmin.set_aside`` and handed back, unopened, to
    ``EffectAdmin.put_back``. Its contents belong to the effect system that
    made it; ``SceneManager`` only carries it in the Overlay's scene stack
    entry.
    """

    __slots__ = ()


class EffectAdmin:
    """Scene-transition-facing effect interface, reserved for ``SceneManager``.

    Carries the operations ``EffectControls`` deliberately sheds so rules never
    see them: setting a covered scene's effects aside for an Overlay, putting
    them back on ``pop``, and starting a booted scene on Split.
    The active scene's local effects and declared packs go to the Active
    scene namespace instead.
    ``SceneManager`` holds an injected ``EffectAdmin`` handle (wired to the same
    instance as ``state.effect_controls``, e.g. the single ``EffectManager``)
    and drives every transition call through it, never through
    ``state.effect_controls``. All three methods raise ``NotImplementedError``
    by default.
    """

    def reset_merge_strategies(self) -> None:
        """Reset every registered scope key's merge strategy to ``SPLIT``.

        Called by ``SceneManager.activate_boot_scene`` so the boot scene starts
        on Split.
        """
        raise NotImplementedError

    def set_aside(self) -> HeldEffects:
        """Take every running effect and the merge strategies out of play, together.

        Afterwards no effect is running, so scopes go dark on the next tick,
        and every scope is on ``SPLIT``. Held effects are neither updated nor
        rendered, and effect calls (including a stop on ``Scope.ALL``) don't
        reach them; their receipts stay valid. Called by
        ``SceneManager._do_overlay``; the result rides in the Overlay's scene
        stack entry.
        """
        raise NotImplementedError

    def put_back(self, held: HeldEffects) -> None:
        """Make *held*'s effects the running set again and restore its merge strategies.

        Expects no effect to be running (the Overlay's own were stopped
        first). Held effects resume from where they froze; any whose receipt
        was stopped while held is removed on the next tick, as usual. Called
        by ``SceneManager._do_pop`` with the popped entry's bundle.
        """
        raise NotImplementedError
