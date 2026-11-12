"""The SceneRuntime: the engine's matched set for running scenes, built once.

Sits above ``engine.scene`` and ``engine.pack_catalog`` in the engine's import
graph (the catalog imports the scene module). Imports nothing from
``hardware`` or ``app``: what the device offers arrives as the engine's own
``EffectOutput`` and ``NetworkControls`` abstractions.
"""

from __future__ import annotations

from engine.effects.manager import EffectManager
from engine.effects.output import EffectOutput
from engine.events import Event
from engine.namespace import ActiveSceneNamespace
from engine.pack_catalog import PackCatalog
from engine.scene import SceneManager
from engine.state import NetworkControls, SceneControls, SceneReboot
from engine.timer import Timer

__all__ = ["SceneRuntime"]


class SceneRuntime:
    """One Active scene namespace, the effect system resolving through it, and the scene manager.

    Built from *catalog* and what the device offers: its effect *outputs*,
    *network_controls*, *capabilities* and *scene_reboot* port. *clock* is
    the one clock the scene and its effects run on; omitted, a wall-clock
    ``Timer`` is built. Because it builds every part itself, the namespace
    effects resolve names through is always the one transitions install
    Scene views into, and effects always update on the scene's clock.

    Driving it::

        runtime.activate_boot_scene(name)
        while True:
            runtime.advance_clock()     # first, so the whole tick reads its time
            runtime.queue_event(event)  # zero or more per tick
            runtime.update()
    """

    __slots__ = ("_clock", "_effect_manager", "_namespace", "_scene_manager")

    def __init__(
        self,
        catalog: PackCatalog,
        outputs: list[EffectOutput],
        network_controls: NetworkControls,
        capabilities: frozenset[str],
        scene_reboot: SceneReboot,
        clock: Timer | None = None,
    ) -> None:
        self._clock: Timer = clock if clock is not None else Timer()
        self._namespace = ActiveSceneNamespace(catalog.effect_registry, catalog.pack_sounds)
        self._effect_manager = EffectManager(namespace=self._namespace, outputs=outputs)
        self._scene_manager = SceneManager(
            self._effect_manager,
            network_controls,
            capabilities,
            catalog.rule_registry,
            catalog.scene_registry,
            self._effect_manager,
            scene_reboot,
        )

    def activate_boot_scene(self, name: str) -> None:
        """Make *name* the active scene, at once, with every scope on Split.

        Raises:
            ValueError: *name* is not a registered scene, or a scene is
                already active.
            MissingCapabilityError: the device can't run *name*; nothing is
                activated.
        """
        self._scene_manager.activate_boot_scene(name)

    @property
    def has_active_scene(self) -> bool:
        """Whether a scene is active, so a queued event would reach its rules."""
        return self._scene_manager.active_state is not None

    def queue_event(self, event: Event) -> None:
        """Queue *event* for the active scene's rules on the next ``update``.

        Dropped when no scene is active.
        """
        state = self._scene_manager.active_state
        if state is not None:
            state.queue_event(event)

    def advance_clock(self) -> None:
        """Advance the clock to this tick, whether or not a scene is active.

        Call it once per tick, before anything reads ``elapsed`` or ``total``,
        so everything the tick drives sees the same, current time.
        """
        self._clock.update()

    def update(self) -> None:
        """Run one tick: dispatch queued events, apply a pending Overlay or pop, update effects.

        The top scene's game time moves on by the clock's elapsed time for
        this tick.
        """
        self._scene_manager.update(self._clock.elapsed)
        self._effect_manager.update(self._clock)

    @property
    def elapsed(self) -> float:
        """The clock's elapsed time for the tick, as of the last :meth:`advance_clock`."""
        return self._clock.elapsed

    @property
    def total(self) -> float:
        """The clock's running total of elapsed time, as of the last :meth:`advance_clock`."""
        return self._clock.total

    @property
    def scene_controls(self) -> SceneControls:
        """The ``SceneControls`` the active scene's rules hold: Overlay, pop and Reboot."""
        return self._scene_manager

    @property
    def namespace(self) -> ActiveSceneNamespace:
        """The Active scene namespace, holding the active scene's Scene view."""
        return self._namespace
