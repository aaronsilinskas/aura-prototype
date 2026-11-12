from __future__ import annotations

__all__ = [
    "EffectAdmin",
    "HeldEffects",
    "SceneView",
]

TYPE_CHECKING = False

if TYPE_CHECKING:
    from engine.scene import SceneLocalRegistry


class SceneView:
    """What the Active scene namespace holds for one scene.

    The scene's local effects (``None`` when it has none), its local sounds
    as a bare ``{stem: path}`` map, and the names of the effect packs it
    declares. Carried by every ``EffectAdmin`` step, which installs it.
    """

    __slots__ = ("declared_packs", "local_effects", "local_sounds")

    def __init__(
        self,
        local_effects: SceneLocalRegistry | None,
        local_sounds: dict[str, str],
        declared_packs: frozenset[str],
    ) -> None:
        self.local_effects = local_effects
        self.local_sounds = local_sounds
        self.declared_packs = declared_packs


class HeldEffects:
    """A covered scene's running effects and merge strategies, set aside together.

    Returned by ``EffectAdmin.cover`` and handed back, unopened, to
    ``EffectAdmin.uncover``. Its contents belong to the effect system that
    made it; ``SceneManager`` only carries it in the Overlay's scene stack
    entry.
    """

    __slots__ = ()


class EffectAdmin:
    """Scene-transition-facing effect interface, reserved for ``SceneManager``.

    Carries the operations ``EffectControls`` deliberately sheds so rules never
    see them: one step per transition, each installing the ``SceneView`` it is
    given into the Active scene namespace (ADR-0008). ``SceneManager`` makes
    exactly one of these calls per transition, never reaching the effect
    system through a stack entry's ``state.effect_controls``. All three steps
    raise ``NotImplementedError`` by default.
    """

    def enter_boot_scene(self, view: SceneView) -> None:
        """Put every scope on ``SPLIT``, then install the boot scene's *view*."""
        raise NotImplementedError

    def cover(self, view: SceneView) -> HeldEffects:
        """Set the running effects and merge strategies aside, then install the Overlay's *view*.

        Afterwards no effect is running, so scopes go dark on the next tick,
        and every scope is on ``SPLIT``. Held effects are neither updated nor
        rendered, and effect calls (including a stop on ``Scope.ALL``) don't
        reach them; their receipts stay valid. The result rides in the
        Overlay's scene stack entry until ``uncover``.
        """
        raise NotImplementedError

    def uncover(self, held: HeldEffects, view: SceneView) -> None:
        """Stop every running effect, put *held* back, then reinstall the covered scene's *view*.

        The stopped effects are the Overlay's own. *held*'s effects resume
        from where they froze, under their merge strategies; any whose
        receipt was stopped while held is removed on the next tick, as usual.
        """
        raise NotImplementedError
