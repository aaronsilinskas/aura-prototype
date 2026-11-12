"""Behaviour tests for the SceneRuntime, built from ``pack_tree`` catalogs.

Each test builds the runtime over recording outputs and checks what is
drawn, what a scene's rules hear, what resolves and what raises.
"""

from __future__ import annotations

import os
import tracemalloc

import pytest

import engine
from engine.capabilities import MissingCapabilityError
from engine.effects.output import EffectOutput
from engine.engine import GameRule
from engine.events import Event, EventGroup
from engine.namespace import ActiveSceneNamespace
from engine.pack_catalog import PackCatalog
from engine.packs import RegistryError
from engine.scene_runtime import SceneRuntime
from engine.state import GameState, Scope
from engine.tests.effects.helpers import SpyEffectOutput
from engine.tests.helpers import RecordingSceneReboot, make_scene_runtime
from engine.timer import Timer

_GROUP = EventGroup("runtime")
_PAINT = Event(_GROUP, "paint")

_RED = 0xFF0000

_COLOR_EFFECTS = {
    "red": (
        "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
        "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
    ),
}

_GAME_RULE_SOURCE = "from engine.engine import GameRule\nRULE = GameRule()\n"

_COLOR = [{"name": "color", "version": "1.0"}]

_ENGINE_SOURCES = os.path.join(os.path.dirname(engine.__file__), "*")
"""Every engine source file: the ones a steady-state update must not grow."""
_ENGINE_TESTS = os.path.join(os.path.dirname(engine.__file__), "tests", "*")


class _Cover(Event):
    """The event a test's base rule answers by requesting the 'cover' Overlay."""


class _Tick(Event):
    """A steady-state tick's event, which no test rule handles."""


class _StepClock(Timer):
    """A clock that advances by a fixed *step* on every update."""

    def __init__(self, step: float) -> None:
        super().__init__()
        self._step = step

    def update(self) -> None:
        self.elapsed = self._step
        self.total += self._step


def _catalog(pack_tree) -> PackCatalog:
    """Scan a 'base' scene and a 'cover' Overlay, each with its own rule pack.

    Both declare the 'color' effect pack; 'base' carries the scene sound
    'win', 'cover' the sound 'lose'. 'tilt' needs an accelerometer.
    """
    return pack_tree.scan(
        effect_packs={"color": _COLOR_EFFECTS},
        rule_packs={
            "base_rules": {"rule": _GAME_RULE_SOURCE},
            "cover_rules": {"rule": _GAME_RULE_SOURCE},
        },
        scenes={
            "base": {
                "effect_packs": _COLOR,
                "rule_packs": [{"name": "base_rules", "version": "1.0"}],
                "sounds": ["win"],
            },
            "cover": {
                "effect_packs": _COLOR,
                "rule_packs": [{"name": "cover_rules", "version": "1.0"}],
                "sounds": ["lose"],
            },
            "tilt": {"requires": ["accelerometer"]},
        },
    )


def _rule(catalog: PackCatalog, pack: str) -> GameRule:
    """The one rule of *pack*, the same instance its scene runs."""
    return catalog.rule_registry.get(pack, "rule", GameRule)


def _paint_red(event: Event, state: GameState) -> None:
    state.effect_controls.set_effect(Scope.PERSONAL, "color.red", {})


def _runtime(
    catalog: PackCatalog,
    output: SpyEffectOutput | None = None,
    *,
    clock: Timer | None = None,
    scene_reboot: RecordingSceneReboot | None = None,
) -> SceneRuntime:
    outputs: list[EffectOutput] = [output] if output is not None else []
    return make_scene_runtime(catalog, outputs, scene_reboot=scene_reboot, clock=clock)


def _personal_output() -> SpyEffectOutput:
    return SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])


def _drawn(output: SpyEffectOutput) -> list[int]:
    _, composed = output.update_pixels_calls[-1]
    return list(composed)


def _resolves_clip(namespace: ActiveSceneNamespace, name: str) -> bool:
    try:
        namespace.resolve_clip(name)
    except RegistryError:
        return False
    return True


def test_a_booted_scenes_effects_draw_on_the_outputs_after_an_update(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    _rule(catalog, "base_rules").on(Event, _paint_red)
    output = _personal_output()
    runtime = _runtime(catalog, output)
    runtime.activate_boot_scene("base")

    runtime.queue_event(_PAINT)
    runtime.update()

    assert _drawn(output) == [_RED] * 4


# ---------------------------------------------------------------------------
# Activating the boot scene
# ---------------------------------------------------------------------------


def test_activating_an_unknown_boot_scene_raises(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree))

    with pytest.raises(ValueError, match="nowhere"):
        runtime.activate_boot_scene("nowhere")


def test_activating_a_boot_scene_the_device_cannot_run_raises_and_activates_nothing(
    pack_tree,
) -> None:
    catalog = _catalog(pack_tree)
    heard: list[Event] = []
    _rule(catalog, "base_rules").on(Event, lambda event, state: heard.append(event))
    runtime = _runtime(catalog)

    with pytest.raises(MissingCapabilityError, match="accelerometer"):
        runtime.activate_boot_scene("tilt")
    runtime.activate_boot_scene("base")
    runtime.queue_event(_PAINT)
    runtime.update()

    assert heard == [_PAINT]


def test_activating_a_second_boot_scene_raises(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree))
    runtime.activate_boot_scene("base")

    with pytest.raises(ValueError, match="already active"):
        runtime.activate_boot_scene("cover")


# ---------------------------------------------------------------------------
# Queuing events
# ---------------------------------------------------------------------------


def test_an_event_queued_with_a_scene_active_reaches_its_rules_on_the_next_update(
    pack_tree,
) -> None:
    catalog = _catalog(pack_tree)
    heard: list[Event] = []
    _rule(catalog, "base_rules").on(Event, lambda event, state: heard.append(event))
    runtime = _runtime(catalog)
    runtime.activate_boot_scene("base")

    runtime.queue_event(_PAINT)
    heard_before_update = list(heard)
    runtime.update()

    assert (heard_before_update, heard) == ([], [_PAINT])


def test_an_event_queued_with_no_scene_active_is_dropped(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    heard: list[Event] = []
    _rule(catalog, "base_rules").on(Event, lambda event, state: heard.append(event))
    runtime = _runtime(catalog)

    runtime.queue_event(_PAINT)
    runtime.update()
    runtime.activate_boot_scene("base")
    runtime.update()

    assert heard == []


def test_a_scene_is_active_only_once_the_boot_scene_is_activated(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree))
    before_boot = runtime.has_active_scene

    runtime.activate_boot_scene("base")

    assert (before_boot, runtime.has_active_scene) == (False, True)


# ---------------------------------------------------------------------------
# One update: dispatch, then transition, then effects
# ---------------------------------------------------------------------------


def test_an_overlay_requested_during_dispatch_covers_the_scene_within_the_same_update(
    pack_tree,
) -> None:
    catalog = _catalog(pack_tree)
    base_rule = _rule(catalog, "base_rules")
    base_rule.on(Event, _paint_red)
    base_rule.on(_Cover, lambda event, state: state.scene_controls.overlay("cover"))
    output = _personal_output()
    runtime = _runtime(catalog, output)
    runtime.activate_boot_scene("base")
    runtime.queue_event(_PAINT)
    runtime.update()
    output.update_pixels_calls.clear()

    runtime.queue_event(_Cover(_GROUP, "cover"))
    runtime.update()

    assert output.update_pixels_calls == []


def test_a_pop_requested_during_dispatch_draws_the_revealed_scenes_effects_in_the_same_update(
    pack_tree,
) -> None:
    catalog = _catalog(pack_tree)
    _rule(catalog, "base_rules").on(Event, _paint_red)
    _rule(catalog, "cover_rules").on(Event, lambda event, state: state.scene_controls.pop())
    output = _personal_output()
    runtime = _runtime(catalog, output)
    runtime.activate_boot_scene("base")
    runtime.queue_event(_PAINT)
    runtime.update()
    runtime.scene_controls.overlay("cover")
    runtime.update()
    output.update_pixels_calls.clear()

    runtime.queue_event(_PAINT)
    runtime.update()

    assert _drawn(output) == [_RED] * 4


# ---------------------------------------------------------------------------
# Elapsed
# ---------------------------------------------------------------------------


def test_elapsed_follows_the_clock_given_at_construction(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree), clock=_StepClock(0.25))
    runtime.activate_boot_scene("base")

    runtime.update()

    assert runtime.elapsed == 0.25


def test_total_accumulates_the_clocks_elapsed_time_across_updates(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree), clock=_StepClock(0.25))
    runtime.activate_boot_scene("base")

    runtime.update()
    runtime.update()

    assert runtime.total == 0.5


def test_the_clock_does_not_advance_while_no_scene_is_active(pack_tree) -> None:
    runtime = _runtime(_catalog(pack_tree), clock=_StepClock(0.25))

    runtime.update()

    assert runtime.elapsed == 0.0


def test_a_scenes_rules_see_the_elapsed_time_the_runtime_reports(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    seen: list[float] = []
    _rule(catalog, "base_rules").on(Event, lambda event, state: seen.append(state.elapsed))
    runtime = _runtime(catalog, clock=_StepClock(0.25))
    runtime.activate_boot_scene("base")

    runtime.queue_event(_PAINT)
    runtime.update()

    assert seen == [0.25]


# ---------------------------------------------------------------------------
# The Active scene namespace
# ---------------------------------------------------------------------------


def test_the_namespace_resolves_the_active_scenes_names_across_boot_overlay_and_pop(
    pack_tree,
) -> None:
    runtime = _runtime(_catalog(pack_tree))
    namespace = runtime.namespace

    def resolvable() -> tuple[bool, bool]:
        return _resolves_clip(namespace, "scene.win"), _resolves_clip(namespace, "scene.lose")

    runtime.activate_boot_scene("base")
    at_boot = resolvable()
    runtime.scene_controls.overlay("cover")
    runtime.update()
    under_overlay = resolvable()
    runtime.scene_controls.pop()
    runtime.update()
    after_pop = resolvable()

    assert (at_boot, under_overlay, after_pop) == ((True, False), (False, True), (True, False))


# ---------------------------------------------------------------------------
# SceneControls
# ---------------------------------------------------------------------------


def test_the_runtimes_scene_controls_cover_the_active_scene(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    _rule(catalog, "base_rules").on(Event, _paint_red)
    output = _personal_output()
    runtime = _runtime(catalog, output)
    runtime.activate_boot_scene("base")
    runtime.queue_event(_PAINT)
    runtime.update()
    output.update_pixels_calls.clear()

    runtime.scene_controls.overlay("cover")
    runtime.update()

    assert output.update_pixels_calls == []


def test_the_runtimes_scene_controls_pop_back_to_the_covered_scene(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    heard: list[str] = []
    _rule(catalog, "base_rules").on(Event, lambda event, state: heard.append("base"))
    _rule(catalog, "cover_rules").on(Event, lambda event, state: heard.append("cover"))
    runtime = _runtime(catalog)
    runtime.activate_boot_scene("base")
    runtime.scene_controls.overlay("cover")
    runtime.update()

    runtime.scene_controls.pop()
    runtime.update()
    runtime.queue_event(_PAINT)
    runtime.update()

    assert heard == ["base"]


def test_the_runtimes_scene_controls_reboot_through_the_scene_reboot_port(pack_tree) -> None:
    reboot = RecordingSceneReboot()
    runtime = _runtime(_catalog(pack_tree), scene_reboot=reboot)
    runtime.activate_boot_scene("base")

    runtime.scene_controls.reboot_into("cover")

    assert reboot.reboot_into_calls == ["cover"]


# ---------------------------------------------------------------------------
# Steady-state allocation
# ---------------------------------------------------------------------------


def test_steady_state_updates_accumulate_no_engine_memory(pack_tree) -> None:
    catalog = _catalog(pack_tree)
    _rule(catalog, "base_rules").on(Event, _paint_red)
    runtime = _runtime(catalog, _personal_output(), clock=_StepClock(0.25))
    runtime.activate_boot_scene("base")
    runtime.queue_event(_PAINT)
    runtime.update()
    tick = _Tick(_GROUP, "tick")  # heard by no handler, as most ticks' events are
    for _ in range(3):  # let every buffer and queue slot reach its steady size
        runtime.queue_event(tick)
        runtime.update()

    engine_files = [
        tracemalloc.Filter(True, _ENGINE_SOURCES),
        tracemalloc.Filter(False, _ENGINE_TESTS),  # the spy output records every frame
    ]
    tracemalloc.start()
    try:
        # Traced from here, a list the effect system clears and refills each
        # tick holds one live block; only what accumulates tick on tick counts.
        for _ in range(10):
            runtime.queue_event(tick)
            runtime.update()
        before = tracemalloc.take_snapshot().filter_traces(engine_files)
        for _ in range(100):
            runtime.queue_event(tick)
            runtime.update()
        after = tracemalloc.take_snapshot().filter_traces(engine_files)
    finally:
        tracemalloc.stop()

    grown = [stat for stat in after.compare_to(before, "lineno") if stat.size_diff > 0]
    assert grown == [], "\n".join(str(stat) for stat in grown)
