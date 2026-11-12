from unittest.mock import ANY

import pytest

from effects.effect import EffectVerb
from engine.effects.admin import SceneView
from engine.effects.manager import EffectManager, VerbKeyError
from engine.effects.merge import ADDITIVE, SPLIT
from engine.events import EffectEvent
from engine.namespace import CLIP, ActiveSceneNamespace, MissingPrefixError, UndeclaredPackError
from engine.pack_catalog import PackCatalog
from engine.packs import PackRegistry, UnknownItemError
from engine.state import Scope
from engine.tests.effects.helpers import (
    AudioClipEffectBuilder,
    CapturingEffectBuilder,
    RenderLengthProbeEffectBuilder,
    SpyEffectBuilder,
    SpyEffectOutput,
    VerbFiringPixels,
)
from engine.timer import Timer

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _stub_item() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _spy_item() -> str:
    return "from engine.tests.effects.helpers import SpyEffectBuilder\nBUILD = SpyEffectBuilder()\n"


def _make_stub_registry(pack_tree) -> PackRegistry:
    """Return a scanned PackRegistry with a 'stub' pack providing common test effects."""
    return pack_tree.scan(
        effect_packs={"stub": {"fire": _stub_item(), "ice": _stub_item(), "shock": _stub_item()}}
    ).effect_registry


def _view(*declared: str, local_sounds: dict[str, str] | None = None) -> SceneView:
    """A Scene view with no local effects, *local_sounds*, declaring the packs *declared*."""
    return SceneView(None, local_sounds or {}, frozenset(declared))


def _make_timer() -> Timer:
    return Timer()


def _make_manager(registry, outputs, allowed=None) -> EffectManager:
    """Construct an EffectManager that has entered a boot scene.

    The scene has no locals and declares every pack *registry* knows, unless
    *allowed* names the declared packs instead.
    """
    manager = EffectManager(namespace=ActiveSceneNamespace(registry, {}), outputs=outputs)
    declared = frozenset(registry.names()) if allowed is None else allowed
    manager.enter_boot_scene(SceneView(None, {}, declared))
    return manager


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_manager_with_no_outputs_updates_without_error() -> None:
    manager = _make_manager(registry=PackRegistry(), outputs=[])
    manager.update(_make_timer())


# ---------------------------------------------------------------------------
# update — go-dark signal when no effects are active
# ---------------------------------------------------------------------------


def test_update_with_no_effects_sends_go_dark_to_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())

    assert output.update_pixels_calls == []
    assert output.clear_pixels_calls == ["personal"]


def test_update_with_no_effects_sends_go_dark_to_all_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert output_a.clear_pixels_calls == ["personal"]
    assert output_b.clear_pixels_calls == ["directional"]


def test_update_sends_go_dark_every_tick_when_no_effects_are_active() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output.clear_pixels_calls == ["personal", "personal"]


def test_update_delivers_one_composed_frame_to_output_on_every_tick(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 2


# ---------------------------------------------------------------------------
# set_effect + update — slice 2
# ---------------------------------------------------------------------------


def test_set_effect_delivers_one_frame_to_matching_output(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_set_effect_nonmatching_output_receives_go_dark(pack_tree) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == []
    assert output_b.clear_pixels_calls == ["directional"]


# ---------------------------------------------------------------------------
# set_effect twice — slice 3
# ---------------------------------------------------------------------------


def test_set_effect_twice_replaces_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.set_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[1])]


def test_set_effect_twice_first_effect_not_advanced(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    registry = pack_tree.scan(
        effect_packs={"spy": {"fire": _spy_item(), "ice": _spy_item()}}
    ).effect_registry
    manager = _make_manager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", {})
    manager.set_effect(Scope.PERSONAL, "spy.ice", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    manager.update(_make_timer())

    effect_a = fire_builder.created[0]
    assert effect_a.update_count == 0


# ---------------------------------------------------------------------------
# out-of-scope go-dark — slice 6
# ---------------------------------------------------------------------------


def test_out_of_scope_output_receives_go_dark_each_frame(pack_tree) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == []
    assert output_b.clear_pixels_calls == ["directional", "directional"]


# ---------------------------------------------------------------------------
# effect events — slice 8
# ---------------------------------------------------------------------------


def test_effect_event_reaches_matching_scope_output(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "events": {
                "shock": (
                    "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                    "BUILD = EventFiringEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])

    receipt = manager.set_effect(Scope.PERSONAL, "events.shock", {})
    manager.update(_make_timer())

    assert output.handle_event_calls == [
        (EffectEvent("events", "shock", EffectVerb.START), frozenset({"personal"}), ANY, receipt),
        (
            EffectEvent("events", "shock", VerbFiringPixels.FIRED),
            frozenset({"personal"}),
            ANY,
            receipt,
        ),
    ]


def test_effect_event_does_not_reach_out_of_scope_output(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "events": {
                "shock": (
                    "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                    "BUILD = EventFiringEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=registry, outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "events.shock", {})
    manager.update(_make_timer())

    assert output_b.handle_event_calls == []


# ---------------------------------------------------------------------------
# resolution — slice 9
# ---------------------------------------------------------------------------


def test_resolution_equals_max_min_resolution_of_matching_outputs(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "capture": {
                "fire": (
                    "from engine.tests.effects.helpers import CapturingEffectBuilder\n"
                    "BUILD = CapturingEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    output_a = SpyEffectOutput(min_resolution=32, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=64, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "capture.fire", {})

    builder = registry.get("capture", "fire", CapturingEffectBuilder)
    assert builder.last_config.resolution == 64


def test_resolution_falls_back_to_default_when_no_outputs_match(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "capture": {
                "fire": (
                    "from engine.tests.effects.helpers import CapturingEffectBuilder\n"
                    "BUILD = CapturingEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    manager = _make_manager(registry=registry, outputs=[])

    manager.set_effect(Scope.PERSONAL, "capture.fire", {})

    builder = registry.get("capture", "fire", CapturingEffectBuilder)
    assert builder.last_config.resolution == 16


# ---------------------------------------------------------------------------
# add_effect — slice 4
# ---------------------------------------------------------------------------


def test_add_effect_after_set_effect_delivers_a_single_composed_frame(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_add_effect_both_effects_advanced_on_each_update(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    registry = pack_tree.scan(
        effect_packs={"spy": {"fire": _spy_item(), "ice": _spy_item()}}
    ).effect_registry
    manager = _make_manager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", {})
    manager.add_effect(Scope.PERSONAL, "spy.ice", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    ice_builder = registry.get("spy", "ice", SpyEffectBuilder)
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert fire_builder.created[0].update_count == 2
    assert ice_builder.created[0].update_count == 2


def test_add_effect_on_empty_scope_delivers_one_frame(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_add_effect_layers_split_two_effects_side_by_side_in_one_buffer(pack_tree) -> None:
    """Split routing: layering two effects on one scope shows both, oldest-first,

    each in its own contiguous slice of the composed region -- not just the
    topmost effect.
    """
    registry = pack_tree.scan(
        effect_packs={
            "color": {
                "red": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
                ),
                "blue": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
                ),
            }
        }
    ).effect_registry
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])

    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.update(_make_timer())

    _, composed = output.update_pixels_calls[0]
    assert list(composed) == [0xFF0000] * 5 + [0x0000FF] * 5


def test_render_runs_after_merge_strategy_sizes_the_buffer(pack_tree) -> None:
    """Split's prepare_buffers partitions each buffer before an effect renders into it."""
    registry = pack_tree.scan(
        effect_packs={
            "probe": {
                "beam": (
                    "from engine.tests.effects.helpers import RenderLengthProbeEffectBuilder\n"
                    "BUILD = RenderLengthProbeEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])

    manager.add_effect(Scope.PERSONAL, "probe.beam", {})
    manager.add_effect(Scope.PERSONAL, "probe.beam", {})
    manager.update(_make_timer())

    builder = registry.get("probe", "beam", RenderLengthProbeEffectBuilder)
    assert builder.observed_lengths == [5, 5]


# ---------------------------------------------------------------------------
# stop_effect — slice 5
# ---------------------------------------------------------------------------


def test_stop_effect_causes_go_dark_on_next_update(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1
    assert output.clear_pixels_calls[-1] == "personal"


def test_stop_effect_clears_stacked_effects(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_stop_effect_does_not_affect_other_scopes(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.set_effect(Scope.DIRECTIONAL, "stub.ice", {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_directional.update_pixels_calls == [
        ("directional", output_directional.created_buffers[0])
    ]


# ---------------------------------------------------------------------------
# shared effect dedup — slice 7
# ---------------------------------------------------------------------------


def test_shared_effect_advanced_once_per_frame_for_composite_scope(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.ALL])
    registry = pack_tree.scan(effect_packs={"spy": {"fire": _spy_item()}}).effect_registry
    manager = _make_manager(registry=registry, outputs=[output])

    manager.set_effect(Scope.ALL, "spy.fire", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    manager.update(_make_timer())

    assert fire_builder.created[0].update_count == 1


def test_each_output_receives_one_frame_for_composite_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1


def test_each_output_gets_distinct_buffer_for_composite_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    _, personal_buf = output_personal.update_pixels_calls[0]
    _, directional_buf = output_directional.update_pixels_calls[0]
    assert personal_buf is not directional_buf


def test_stop_effect_all_sends_go_dark_to_every_output(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1
    assert output_personal.clear_pixels_calls[-1] == "personal"
    assert output_directional.clear_pixels_calls[-1] == "directional"


# ---------------------------------------------------------------------------
# scope subtraction — flat list refactor (#61)
# ---------------------------------------------------------------------------


def test_set_effect_on_partial_scope_leaves_other_scope_effects_running(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    output_global = SpyEffectOutput(min_resolution=10, scopes=[Scope.Global.MAIN])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional, output_global],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.set_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1
    assert len(output_global.update_pixels_calls) == 1


def test_stop_effect_on_partial_scope_continues_rendering_on_remaining_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls == []
    assert len(output_directional.update_pixels_calls) == 1


def test_stop_effect_with_broader_scope_removes_narrower_effect_completely(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls == []
    assert output_directional.update_pixels_calls == []


def test_add_effect_does_not_stop_effects_already_running_in_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1


# ---------------------------------------------------------------------------
# EffectReceipt generation (#63)
# ---------------------------------------------------------------------------


def test_two_add_effect_calls_return_different_receipts(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.ice", {})

    assert receipt_a is not receipt_b
    assert receipt_a.id != receipt_b.id


# ---------------------------------------------------------------------------
# receipt.stop() + deferred-stop (#64)
# ---------------------------------------------------------------------------


def test_stop_effect_by_receipt_stops_the_matching_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_stop_effect_by_receipt_leaves_other_effects_running(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    receipt_a.stop()
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_stop_effect_stops_the_receipt_of_an_effect_it_removes(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    manager.stop_effect(Scope.PERSONAL)

    assert receipt.is_stopped()


def test_set_effect_stops_the_receipt_of_the_effect_it_replaces(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    replaced = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    manager.set_effect(Scope.PERSONAL, "stub.ice", {})

    assert replaced.is_stopped()


def test_stop_effect_keeps_a_narrowed_effect_rendering_with_its_receipt_not_stopped(
    pack_tree,
) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )
    receipt = manager.add_effect(Scope.ALL, "stub.fire", {})

    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert not receipt.is_stopped()
    assert len(output_directional.update_pixels_calls) == 1


def test_stop_effect_by_receipt_with_stale_receipt_is_silent_noop(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    receipt.stop()  # second call — idempotent
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


# ---------------------------------------------------------------------------
# lifecycle events — start/stop (#58)
# ---------------------------------------------------------------------------


def test_add_effect_fires_start_event_to_matching_output(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"personal"}), ANY, receipt)
    ]


def test_starting_an_effect_announces_the_engine_start_verb(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls[0][0].verb is EffectVerb.START


def test_stopping_an_effect_announces_the_engine_stop_verb(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls[0][0].verb is EffectVerb.STOP


def test_add_effect_start_event_not_delivered_to_out_of_scope_output(pack_tree) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output_a, output_b])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output_b.handle_event_calls == []


def test_add_effect_does_not_fire_stop_for_existing_effects(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "ice", EffectVerb.START), frozenset({"personal"}), ANY, ice_receipt)
    ]


def test_add_effect_fires_start_event_unconditionally_for_duplicate_name(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"personal"}), ANY, receipt_a),
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"personal"}), ANY, receipt_b),
    ]


def test_stop_effect_fires_stop_event_to_matching_output(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, receipt)
    ]


def test_stop_effect_fires_stop_for_each_effect_in_scope(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", EffectVerb.STOP), frozenset({"personal"}), ANY, ice_receipt),
    ]


def test_set_effect_fires_stop_then_start_when_replacing_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", EffectVerb.START), frozenset({"personal"}), ANY, ice_receipt),
    ]


def test_set_effect_fires_stop_only_to_outputs_in_call_time_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.ALL, "stub.fire", {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", {})

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", EffectVerb.START), frozenset({"personal"}), ANY, ice_receipt),
    ]
    assert output_directional.handle_event_calls == []


def test_stop_effect_with_broader_scope_fires_stop_to_all_matching_outputs(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.stop_effect(Scope.ALL)

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, fire_receipt)
    ]
    assert output_directional.handle_event_calls == [
        (
            EffectEvent("stub", "fire", EffectVerb.STOP),
            frozenset({"directional"}),
            ANY,
            fire_receipt,
        )
    ]


def test_stop_effect_by_receipt_fires_stop_event(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    receipt.stop()
    manager.update(_make_timer())

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, receipt)
    ]


def test_stop_effect_by_receipt_only_notifies_outputs_still_serving_the_effect(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.ALL, "stub.fire", {})
    # set_effect(PERSONAL) narrows fire to DIRECTIONAL and fires fire.stop to PERSONAL
    manager.set_effect(Scope.PERSONAL, "stub.ice", {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    # fire is now only on DIRECTIONAL — receipt.stop() should only notify DIRECTIONAL
    fire_receipt.stop()
    manager.update(_make_timer())

    assert output_personal.handle_event_calls == []
    assert output_directional.handle_event_calls == [
        (
            EffectEvent("stub", "fire", EffectVerb.STOP),
            frozenset({"directional"}),
            ANY,
            fire_receipt,
        )
    ]


# ---------------------------------------------------------------------------
# scope forwarding
# ---------------------------------------------------------------------------


def test_handle_event_receives_personal_scope_for_personal_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"personal"}), ANY, receipt)
    ]


def test_handle_event_receives_directional_scope_for_directional_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.DIRECTIONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "ice", EffectVerb.START), frozenset({"directional"}), ANY, receipt)
    ]


def test_handle_event_receives_composite_scope_not_decomposed_leaf(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    receipt = manager.add_effect(Scope.ALL, "stub.fire", {})

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"personal"}), ANY, receipt)
    ]
    assert output_directional.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.START), frozenset({"directional"}), ANY, receipt)
    ]


# ---------------------------------------------------------------------------
# Name resolution errors reach the caller typed (routing lives in test_namespace.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["set_effect", "add_effect"])
def test_unresolvable_effect_name_raises_the_namespace_error(pack_tree, method) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    with pytest.raises(MissingPrefixError):
        getattr(manager, method)(Scope.PERSONAL, "fire", {})


def test_effect_from_a_pack_the_scene_did_not_declare_raises_undeclared_pack(pack_tree) -> None:
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree), outputs=[], allowed=frozenset()
    )

    with pytest.raises(UndeclaredPackError):
        manager.set_effect(Scope.PERSONAL, "stub.fire", {})


# ---------------------------------------------------------------------------
# A failed set_effect leaves the scope unchanged (#1114)
# ---------------------------------------------------------------------------


def test_failed_set_effect_keeps_the_running_effect_rendering(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "stub.missing", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_failed_set_effect_fires_no_stop_event(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "stub.missing", {})

    assert output.handle_event_calls == []


def test_failed_set_effect_adds_no_effect(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    fire_receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "stub.missing", {})
    output.handle_event_calls.clear()
    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", EffectVerb.STOP), frozenset({"personal"}), ANY, fire_receipt)
    ]


def test_failed_set_effect_takes_no_receipt_id(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])
    first = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "stub.missing", {})
    second = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert second.id == first.id + 1


# ---------------------------------------------------------------------------
# Clips resolve when the effect is built (#1116)
# ---------------------------------------------------------------------------


# A verb no test effect emits, and a hand-made twin of the declared FIRED.
_MISFIRED = EffectVerb("misfired")
_HANDMADE_FIRED = EffectVerb("fired")

_VERB_SOURCES = (
    (EffectVerb.START, "EffectVerb.START"),
    (EffectVerb.STOP, "EffectVerb.STOP"),
    (VerbFiringPixels.FIRED, "VerbFiringPixels.FIRED"),
    (_MISFIRED, "EffectVerb('misfired')"),
    (_HANDMADE_FIRED, "EffectVerb('fired')"),
)


def _verb_source(verb: EffectVerb) -> str:
    return next(source for known, source in _VERB_SOURCES if known is verb)


def _clip_item(clips: dict[EffectVerb, str], fires: bool = False) -> str:
    """Source for an effect item whose ``BUILD`` declares *clips* (verb → clip name).

    Its pixels are ``VerbFiringPixels``; with *fires* they emit ``FIRED`` on every update.
    """
    entries = ", ".join(f"{_verb_source(verb)}: {name!r}" for verb, name in clips.items())
    return (
        "from effects.effect import EffectVerb\n"
        "from engine.tests.effects.helpers import AudioClipEffectBuilder, VerbFiringPixels\n"
        + f"BUILD = AudioClipEffectBuilder({{{entries}}}, fires={fires!r})\n"
    )


def _pattern_item(verbs: list[EffectVerb], pixels: bool = True) -> str:
    """Source for an effect item whose ``BUILD`` declares a haptic pattern on each of *verbs*.

    With *pixels* its pixels are non-firing ``VerbFiringPixels``; without, it has none.
    """
    keys = ", ".join(_verb_source(verb) for verb in verbs)
    return (
        "from effects.effect import EffectVerb\n"
        "from engine.tests.effects.helpers import HapticPatternEffectBuilder, VerbFiringPixels\n"
        + f"BUILD = HapticPatternEffectBuilder([{keys}], pixels={pixels!r})\n"
    )


def _make_clip_manager(
    pack_tree, items: dict[str, str], outputs
) -> tuple[EffectManager, PackCatalog]:
    """Manager over pack ``sfx`` (sounds ``boom``, ``chime``) holding *items*.

    The installed scene declares ``sfx`` and has local sound ``cheer``.
    Returns the manager and the scanned catalog.
    """
    root = pack_tree.root("tp_sfx")
    pack_tree.effect_pack(
        root, "sfx", items={"plain": _stub_item(), **items}, sounds=["boom", "chime"]
    )
    pack_tree.scene(root, "arena", sounds=["cheer"])
    catalog = pack_tree.scan_roots(root)
    namespace = ActiveSceneNamespace(catalog.effect_registry, catalog.pack_sounds)
    manager = EffectManager(namespace=namespace, outputs=outputs)
    local_sounds = catalog.scene_registry.get("arena").local_sound_map
    manager.enter_boot_scene(_view("sfx", local_sounds=local_sounds))
    return manager, catalog


def _events(output: SpyEffectOutput) -> list[EffectEvent]:
    return [call[0] for call in output.handle_event_calls]


def test_start_event_carries_the_resolved_clip_for_its_verb(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, catalog = _make_clip_manager(
        pack_tree, {"bang": _clip_item({EffectVerb.START: "sfx.boom"})}, [output]
    )

    manager.set_effect(Scope.PERSONAL, "sfx.bang", {})

    (start,) = _events(output)
    assert start.clip is not None
    assert start.clip.config.name == "sfx.boom"
    assert start.clip.path == catalog.pack_sounds["sfx.boom"]


def test_custom_verb_event_carries_the_resolved_clip_for_its_verb(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, catalog = _make_clip_manager(
        pack_tree,
        {"bang": _clip_item({VerbFiringPixels.FIRED: "scene.cheer"}, fires=True)},
        [output],
    )
    manager.set_effect(Scope.PERSONAL, "sfx.bang", {})

    manager.update(_make_timer())

    fired = _events(output)[-1]
    assert fired.verb is VerbFiringPixels.FIRED
    assert fired.clip is not None
    assert fired.clip.path == catalog.scene_registry.get("arena").local_sound_map["cheer"]


def test_verb_with_no_clip_emits_an_event_with_no_clip(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(
        pack_tree, {"bang": _clip_item({VerbFiringPixels.FIRED: "sfx.boom"})}, [output]
    )

    manager.set_effect(Scope.PERSONAL, "sfx.bang", {})
    manager.stop_effect(Scope.PERSONAL)

    assert [(event.verb, event.clip) for event in _events(output)] == [
        (EffectVerb.START, None),
        (EffectVerb.STOP, None),
    ]


def test_effect_with_no_audio_emits_events_with_no_clip(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(pack_tree, {}, [output])

    manager.set_effect(Scope.PERSONAL, "sfx.plain", {})

    (start,) = _events(output)
    assert start.clip is None


@pytest.mark.parametrize("verb", [EffectVerb.START, VerbFiringPixels.FIRED])
def test_misspelled_clip_raises_from_set_effect_on_any_verb(pack_tree, verb) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(pack_tree, {"bang": _clip_item({verb: "sfx.bomm"})}, [output])

    with pytest.raises(UnknownItemError) as exc_info:
        manager.set_effect(Scope.PERSONAL, "sfx.bang", {})

    assert (exc_info.value.name, exc_info.value.kind) == ("sfx.bomm", CLIP)


def test_misspelled_clip_on_a_custom_verb_leaves_the_scope_unchanged(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(
        pack_tree, {"bang": _clip_item({VerbFiringPixels.FIRED: "sfx.bomm"})}, [output]
    )
    plain_receipt = manager.set_effect(Scope.PERSONAL, "sfx.plain", {})
    output.handle_event_calls.clear()

    with pytest.raises(UnknownItemError):
        manager.set_effect(Scope.PERSONAL, "sfx.bang", {})
    assert output.handle_event_calls == []
    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("sfx", "plain", EffectVerb.STOP), frozenset({"personal"}), ANY, plain_receipt)
    ]


def test_building_leaves_the_shared_playback_configs_unchanged(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, catalog = _make_clip_manager(
        pack_tree, {"bang": _clip_item({EffectVerb.START: "sfx.boom"})}, [output]
    )
    builder = catalog.effect_registry.get("sfx", "bang", AudioClipEffectBuilder)
    declared = builder.clips[EffectVerb.START]

    manager.set_effect(Scope.PERSONAL, "sfx.bang", {})
    manager.add_effect(Scope.PERSONAL, "sfx.bang", {})

    assert builder.clips == {EffectVerb.START: declared}
    assert (declared.name, declared.loop, declared.stops_effect) == ("sfx.boom", False, False)
    starts = _events(output)
    assert starts[0].clip is not None
    assert starts[1].clip is not None
    assert starts[0].clip.config is declared
    assert starts[1].clip.config is declared
    assert starts[0].clip is not starts[1].clip


# ---------------------------------------------------------------------------
# Verb keys are checked when the effect is built (ADR-0006)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["set_effect", "add_effect"])
def test_clip_keyed_on_a_verb_the_effect_never_emits_raises(pack_tree, method) -> None:
    manager, _ = _make_clip_manager(pack_tree, {"bang": _clip_item({_MISFIRED: "sfx.boom"})}, [])

    with pytest.raises(VerbKeyError):
        getattr(manager, method)(Scope.PERSONAL, "sfx.bang", {})


def test_clip_keyed_on_a_hand_made_twin_of_a_declared_verb_raises(pack_tree) -> None:
    manager, _ = _make_clip_manager(
        pack_tree, {"bang": _clip_item({_HANDMADE_FIRED: "sfx.boom"})}, []
    )

    with pytest.raises(VerbKeyError):
        manager.set_effect(Scope.PERSONAL, "sfx.bang", {})


# A scene-local effect that reuses basic.pulse's pixels and keys a clip on
# PulseEffect.PEAK without declaring any verb itself.
_PULSE_WRAPPER_ITEM = (
    "from effects.effect import AudioPlaybackConfig, Effect, EffectAudio\n"
    "from engine.effects.builder import EffectBuilder\n"
    "from packs.effects.basic.helpers.pulse_effect import PulseEffect\n"
    "from packs.effects.basic.pulse import BUILD as PULSE\n"
    "_AUDIO = EffectAudio({PulseEffect.PEAK: AudioPlaybackConfig('sfx.boom', loop=False)})\n"
    "class _Wrapper(EffectBuilder):\n"
    "    def __call__(self, name, config):\n"
    "        return Effect(name, pixels=PULSE(name, config).pixels, audio=_AUDIO)\n"
    "BUILD = _Wrapper()\n"
)

# basic.pulse brightens for 0.5 s by default, so one 0.6 s tick crosses its peak.
_PAST_PULSE_PEAK = 0.6


def test_wrapper_may_key_clips_on_the_verbs_its_reused_pack_pixels_declare(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, catalog = _make_clip_manager(pack_tree, {"warn": _PULSE_WRAPPER_ITEM}, [output])
    manager.set_effect(Scope.PERSONAL, "sfx.warn", {})
    timer = _make_timer()
    timer.elapsed = _PAST_PULSE_PEAK

    manager.update(timer)

    peak = _events(output)[-1]
    assert peak.verb.name == "peak"
    assert peak.clip is not None
    assert peak.clip.path == catalog.pack_sounds["sfx.boom"]


def test_clip_keyed_on_stop_raises_explaining_teardown_is_flush(pack_tree) -> None:
    manager, _ = _make_clip_manager(
        pack_tree, {"bang": _clip_item({EffectVerb.STOP: "sfx.chime"})}, []
    )

    with pytest.raises(VerbKeyError, match="flush"):
        manager.set_effect(Scope.PERSONAL, "sfx.bang", {})


def test_stop_clip_error_names_the_effect_modality_and_emitted_verbs(pack_tree) -> None:
    manager, _ = _make_clip_manager(
        pack_tree, {"bang": _clip_item({EffectVerb.STOP: "sfx.chime"})}, []
    )

    with pytest.raises(VerbKeyError) as exc_info:
        manager.set_effect(Scope.PERSONAL, "sfx.bang", {})

    message = str(exc_info.value)
    for part in ("'sfx.bang'", "clips", "'stop'", "'start'", "'fired'"):
        assert part in message


@pytest.mark.parametrize("method", ["set_effect", "add_effect"])
def test_pattern_keyed_on_a_verb_the_effect_never_emits_raises(pack_tree, method) -> None:
    manager, _ = _make_clip_manager(pack_tree, {"buzz": _pattern_item([_MISFIRED])}, [])

    with pytest.raises(VerbKeyError):
        getattr(manager, method)(Scope.PERSONAL, "sfx.buzz", {})


def test_pattern_keyed_on_stop_builds(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(pack_tree, {"buzz": _pattern_item([EffectVerb.STOP])}, [output])

    manager.set_effect(Scope.PERSONAL, "sfx.buzz", {})

    assert [event.verb for event in _events(output)] == [EffectVerb.START]


def test_effect_without_pixels_can_key_no_custom_verb(pack_tree) -> None:
    manager, _ = _make_clip_manager(
        pack_tree, {"buzz": _pattern_item([VerbFiringPixels.FIRED], pixels=False)}, []
    )

    with pytest.raises(VerbKeyError):
        manager.set_effect(Scope.PERSONAL, "sfx.buzz", {})


def test_verb_key_error_names_the_effect_modality_key_and_emitted_verbs(pack_tree) -> None:
    manager, _ = _make_clip_manager(pack_tree, {"buzz": _pattern_item([_MISFIRED])}, [])

    with pytest.raises(VerbKeyError) as exc_info:
        manager.set_effect(Scope.PERSONAL, "sfx.buzz", {})

    message = str(exc_info.value)
    for part in ("'sfx.buzz'", "patterns", "'misfired'", "'start'", "'stop'", "'fired'"):
        assert part in message


@pytest.mark.parametrize("method", ["set_effect", "add_effect"])
@pytest.mark.parametrize(
    "bad_item",
    [_pattern_item([_MISFIRED]), _clip_item({_MISFIRED: "sfx.boom"})],
    ids=["patterns", "clips"],
)
def test_verb_key_error_leaves_the_scope_unchanged(pack_tree, method, bad_item) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager, _ = _make_clip_manager(pack_tree, {"bad": bad_item}, [output])
    plain_receipt = manager.set_effect(Scope.PERSONAL, "sfx.plain", {})
    output.handle_event_calls.clear()

    with pytest.raises(VerbKeyError):
        getattr(manager, method)(Scope.PERSONAL, "sfx.bad", {})
    assert output.handle_event_calls == []
    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("sfx", "plain", EffectVerb.STOP), frozenset({"personal"}), ANY, plain_receipt)
    ]


# ---------------------------------------------------------------------------
# flush
# ---------------------------------------------------------------------------


def test_update_calls_flush_when_no_effects_are_active() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_update_calls_flush_once_per_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.flush_calls) == 3


def test_update_calls_flush_on_all_outputs_each_tick() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert len(output_a.flush_calls) == 1
    assert len(output_b.flush_calls) == 1


# ---------------------------------------------------------------------------
# clear_pixels — issue #139
# ---------------------------------------------------------------------------


def test_stop_effect_calls_clear_pixels_when_last_effect_stops(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)

    assert output.clear_pixels_calls == ["personal"]


def test_stop_effect_by_receipt_calls_clear_pixels_when_last_effect_stops(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.clear_pixels_calls[0] == "personal"


def test_stop_effect_by_receipt_does_not_call_clear_pixels_when_layered_effect_remains(
    pack_tree,
) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    fire_receipt.stop()
    manager.update(_make_timer())

    assert output.clear_pixels_calls == []


def test_clear_pixels_fires_for_narrowed_key_with_no_remaining_coverage(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)

    assert output_personal.clear_pixels_calls == ["personal"]
    assert output_directional.clear_pixels_calls == []


def test_clear_pixels_not_fired_for_key_still_covered_after_narrowing(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.stop_effect(Scope.PERSONAL)

    # fire still covers directional; ice and fire(personal) both stopped
    # personal is now covered by nothing → clear
    # directional still covered by fire → no clear
    assert output_personal.clear_pixels_calls == ["personal"]
    assert output_directional.clear_pixels_calls == []


def test_update_calls_flush_even_when_effects_are_active(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_update_calls_flush_after_update_pixels_each_tick(pack_tree) -> None:
    call_order: list[str] = []

    class OrderTrackingOutput(SpyEffectOutput):
        def update_pixels(self, scope_key: str, buffer) -> None:
            super().update_pixels(scope_key, buffer)
            call_order.append("update_pixels")

        def flush(self) -> None:
            super().flush()
            call_order.append("flush")

    output = OrderTrackingOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert call_order == ["update_pixels", "flush"]


def test_update_calls_flush_after_clear_pixels_each_tick_when_no_effects_are_active() -> None:
    call_order: list[str] = []

    class OrderTrackingOutput(SpyEffectOutput):
        def clear_pixels(self, scope_key: str) -> None:
            super().clear_pixels(scope_key)
            call_order.append("clear_pixels")

        def flush(self) -> None:
            super().flush()
            call_order.append("flush")

    output = OrderTrackingOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())

    assert call_order == ["clear_pixels", "flush"]


# ---------------------------------------------------------------------------
# per-key create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_called_with_scope_key_on_effect_start(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.create_buffer_key_calls == ["personal"]


def test_create_buffer_called_once_per_matching_key_for_composite_scope(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})

    assert output_personal.create_buffer_key_calls == ["personal"]
    assert output_directional.create_buffer_key_calls == ["directional"]


def test_create_buffer_not_called_for_out_of_scope_output(pack_tree) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output_directional.create_buffer_key_calls == []


def test_scoped_listener_uses_live_keys_after_scope_narrowing(pack_tree) -> None:
    """Effect-triggered events after scope narrowing must reach only remaining-scope outputs."""
    registry = pack_tree.scan(
        effect_packs={
            "evt": {
                "shock": (
                    "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                    "BUILD = EventFiringEffectBuilder()\n"
                )
            }
        }
    ).effect_registry
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(registry=registry, outputs=[output_personal, output_directional])

    manager.add_effect(Scope.ALL, "evt.shock", {})
    manager.stop_effect(Scope.PERSONAL)  # narrows shock: personal key removed
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.update(_make_timer())

    # shock effect fires VerbFiringPixels.FIRED; scoped_listener reads live entry.keys
    # → personal output must NOT receive it after narrowing
    assert not any(
        c[0] == EffectEvent("evt", "shock", VerbFiringPixels.FIRED)
        for c in output_personal.handle_event_calls
    )
    assert any(
        c[0] == EffectEvent("evt", "shock", VerbFiringPixels.FIRED)
        for c in output_directional.handle_event_calls
    )


# ---------------------------------------------------------------------------
# per-key update_pixels
# ---------------------------------------------------------------------------


def test_update_pixels_called_once_per_registered_key_for_multi_key_output(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL, Scope.DIRECTIONAL])
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    called_keys = [key for key, _ in output.update_pixels_calls]
    assert set(called_keys) == {"personal", "directional"}
    assert len(called_keys) == 2  # exactly one call per key, no duplicates


# ---------------------------------------------------------------------------
# receives_pixels — issue #191
# ---------------------------------------------------------------------------


def test_output_with_receives_pixels_false_gets_no_create_buffer(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.create_buffer_key_calls == []


def test_output_with_receives_pixels_false_gets_no_update_pixels(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_output_with_receives_pixels_false_still_gets_flush(pack_tree) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_output_with_receives_pixels_false_flush_called_even_with_no_effects() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = _make_manager(registry=PackRegistry(), outputs=[output])

    manager.update(_make_timer())

    assert len(output.flush_calls) == 1
    assert output.update_pixels_calls == []


def test_pixel_output_alongside_non_pixel_output_both_get_flush(pack_tree) -> None:
    pixel_output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    non_pixel_output = SpyEffectOutput(
        min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False
    )
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[pixel_output, non_pixel_output],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(pixel_output.flush_calls) == 1
    assert len(non_pixel_output.flush_calls) == 1
    assert len(pixel_output.update_pixels_calls) == 1
    assert non_pixel_output.update_pixels_calls == []
    assert non_pixel_output.create_buffer_key_calls == []


# ---------------------------------------------------------------------------
# renders_pixels — issue #191
# ---------------------------------------------------------------------------


def test_effect_with_renders_pixels_false_skips_buffer_allocation(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "nopix": {
                "event": (
                    "from effects.effect import Effect, EffectConfig\n"
                    "from engine.effects.builder import EffectBuilder\n"
                    "class _Builder(EffectBuilder):\n"
                    "    def __call__(self, name, config): return Effect(name=name)\n"
                    "BUILD = _Builder()\n"
                )
            }
        }
    ).effect_registry

    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "nopix.event", {})

    assert output.create_buffer_key_calls == []


def test_effect_with_renders_pixels_false_skips_update_pixels_but_calls_flush(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "nopix": {
                "event": (
                    "from effects.effect import Effect, EffectConfig\n"
                    "from engine.effects.builder import EffectBuilder\n"
                    "class _Builder(EffectBuilder):\n"
                    "    def __call__(self, name, config): return Effect(name=name)\n"
                    "BUILD = _Builder()\n"
                )
            }
        }
    ).effect_registry

    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "nopix.event", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == []
    assert output.clear_pixels_calls == ["personal"]
    assert len(output.flush_calls) == 1


# ---------------------------------------------------------------------------
# EffectReceipt — brightness and loudness from options (#249)
# ---------------------------------------------------------------------------


def test_set_effect_receipt_brightness_defaults_to_one(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert receipt.brightness == 1.0


def test_set_effect_receipt_loudness_defaults_to_one(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert receipt.loudness == 1.0


def test_set_effect_transfers_brightness_from_options(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {"brightness": 0.5})

    assert receipt.brightness == 0.5


def test_set_effect_transfers_loudness_from_options(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {"loudness": 0.25})

    assert receipt.loudness == 0.25


def test_add_effect_transfers_brightness_from_options(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {"brightness": 0.75})

    assert receipt.brightness == 0.75


def test_set_effect_rejects_out_of_range_brightness_option(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "stub.fire", {"brightness": 1.5})


def test_set_effect_rejects_out_of_range_loudness_option(pack_tree) -> None:
    manager = _make_manager(registry=_make_stub_registry(pack_tree), outputs=[])

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "stub.fire", {"loudness": -0.1})


# ---------------------------------------------------------------------------
# set_merge_strategy — issue #587
# ---------------------------------------------------------------------------


def test_set_merge_strategy_takes_effect_starting_next_tick(pack_tree) -> None:
    """Switching from Split to Additive mid-run blends from the very next tick onward."""
    registry = pack_tree.scan(
        effect_packs={
            "color": {
                "red": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
                ),
                "blue": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
                ),
            }
        }
    ).effect_registry
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output])
    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.update(_make_timer())  # still the default Split strategy
    # Composed buffers are mutated in place on the next tick, so snapshot the
    # pixel values now rather than comparing PixelBuffer object identity later.
    _, first_composed = output.update_pixels_calls[0]
    split_snapshot = list(first_composed)

    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    manager.update(_make_timer())

    _, second_composed = output.update_pixels_calls[1]
    assert split_snapshot == [0xFF0000] * 5 + [0x0000FF] * 5
    assert list(second_composed) == [0xFF00FF] * 10


def test_set_merge_strategy_leaves_other_scopes_strategy_unchanged(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "color": {
                "red": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
                ),
                "blue": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
                ),
            }
        }
    ).effect_registry
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = _make_manager(
        registry=registry,
        outputs=[SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL]), output_directional],
    )
    manager.add_effect(Scope.DIRECTIONAL, "color.red", {})
    manager.add_effect(Scope.DIRECTIONAL, "color.blue", {})

    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    manager.update(_make_timer())

    _, composed = output_directional.update_pixels_calls[0]
    assert list(composed) == [0xFF0000] * 5 + [0x0000FF] * 5  # DIRECTIONAL still Split


# ---------------------------------------------------------------------------
# Mirrored outputs — two outputs share a scope key (issue #483)
# ---------------------------------------------------------------------------


def test_two_outputs_sharing_scope_both_receive_frame_on_update(pack_tree) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_a, output_b],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output_a.update_pixels_calls) == 1
    assert len(output_b.update_pixels_calls) == 1


def test_two_outputs_sharing_scope_each_gets_its_own_buffer(pack_tree) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = _make_manager(
        registry=_make_stub_registry(pack_tree),
        outputs=[output_a, output_b],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    _, buf_a = output_a.update_pixels_calls[0]
    _, buf_b = output_b.update_pixels_calls[0]
    assert buf_a is not buf_b


def test_two_outputs_sharing_scope_both_reflect_the_same_receipts_brightness(pack_tree) -> None:
    registry = pack_tree.scan(
        effect_packs={
            "color": {
                "red": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
                )
            }
        }
    ).effect_registry
    output_a = SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])
    manager = _make_manager(registry=registry, outputs=[output_a, output_b])

    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    receipt.brightness = 0.5
    manager.update(_make_timer())

    _, buf_a = output_a.update_pixels_calls[0]
    _, buf_b = output_b.update_pixels_calls[0]
    assert list(buf_a) == list(buf_b) == [0x7F0000] * 4


# ---------------------------------------------------------------------------
# Merge-strategy and held-effects fixtures
# ---------------------------------------------------------------------------


def _make_counting_manager(pack_tree):
    """Return (manager, output) over one PERSONAL output of 4 pixels.

    'count.fx' fills its buffer with its own update count, so a frame shows
    how far it has advanced; 'color.red'/'color.blue' fill solid colors.
    """
    registry = pack_tree.scan(
        effect_packs={
            "count": {
                "fx": (
                    "from engine.tests.effects.helpers import UpdateCountFillEffectBuilder\n"
                    "BUILD = UpdateCountFillEffectBuilder()\n"
                ),
            },
            "color": {
                "red": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
                ),
                "blue": (
                    "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                    "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
                ),
            },
        }
    ).effect_registry
    output = SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])
    return _make_manager(registry=registry, outputs=[output]), output


def _tick(manager, output) -> list | None:
    """Update once; return the PERSONAL frame delivered that tick, or None if it went dark."""
    output.update_pixels_calls.clear()
    manager.update(_make_timer())
    if not output.update_pixels_calls:
        return None
    _, composed = output.update_pixels_calls[-1]
    return list(composed)


_SPLIT_RED_BLUE = [0xFF0000] * 2 + [0x0000FF] * 2
_ADDITIVE_RED_BLUE = [0xFF00FF] * 4


# ---------------------------------------------------------------------------
# EffectAdmin steps — entering the boot scene, covering and uncovering
# ---------------------------------------------------------------------------


def test_entering_the_boot_scene_puts_every_scope_on_split(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)

    manager.enter_boot_scene(_view("color", "count"))

    assert _tick(manager, output) == _SPLIT_RED_BLUE


def test_entering_the_boot_scene_resolves_its_view(pack_tree) -> None:
    registry = _make_stub_registry(pack_tree)
    manager = EffectManager(namespace=ActiveSceneNamespace(registry, {}), outputs=[])

    manager.enter_boot_scene(_view("stub"))

    assert manager.set_effect(Scope.PERSONAL, "stub.fire", {}) is not None


def test_covering_darkens_the_covered_scopes(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.set_effect(Scope.PERSONAL, "count.fx", {})
    _tick(manager, output)

    manager.cover(_view("color"))

    assert _tick(manager, output) is None
    assert output.clear_pixels_calls[-1] == "personal"


def test_covering_tells_each_output_which_effects_are_held(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})

    manager.cover(_view("color"))

    assert [(keys, r) for keys, _, r in output.held_calls] == [(frozenset({"personal"}), receipt)]


def test_covering_fires_no_stop_event_for_the_covered_effects(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    output.handle_event_calls.clear()

    manager.cover(_view("color"))

    assert output.handle_event_calls == []
    assert not receipt.is_stopped()


def test_covering_starts_every_scope_on_split(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)

    manager.cover(_view("color"))
    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})

    assert _tick(manager, output) == _SPLIT_RED_BLUE


def test_covering_resolves_the_overlays_view(pack_tree) -> None:
    manager, _ = _make_counting_manager(pack_tree)

    manager.cover(_view("count"))

    manager.set_effect(Scope.PERSONAL, "count.fx", {})
    with pytest.raises(UndeclaredPackError):
        manager.set_effect(Scope.PERSONAL, "color.red", {})


def test_an_effect_started_while_others_are_held_does_not_join_them(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.set_effect(Scope.PERSONAL, "color.red", {})
    manager.cover(_view("color"))
    manager.set_effect(Scope.PERSONAL, "color.blue", {})

    assert _tick(manager, output) == [0x0000FF] * 4


def test_stopping_every_scope_while_covered_leaves_the_held_effects_untouched(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    manager.cover(_view("color"))
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.ALL)

    assert output.handle_event_calls == [], "no stop event reaches a held effect"
    assert not receipt.is_stopped()


def test_uncovering_stops_the_overlays_own_effects(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    held = manager.cover(_view("color"))
    overlays = manager.set_effect(Scope.PERSONAL, "color.blue", {})
    output.handle_event_calls.clear()

    manager.uncover(held, _view("color"))

    assert overlays.is_stopped()
    assert [call[0].verb for call in output.handle_event_calls] == [EffectVerb.STOP]


def test_uncovering_redraws_the_covered_effects_from_where_they_froze(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.set_effect(Scope.PERSONAL, "count.fx", {})
    _tick(manager, output)
    _tick(manager, output)
    held = manager.cover(_view("count"))
    manager.set_effect(Scope.PERSONAL, "count.fx", {})  # the Overlay's own
    for _ in range(3):
        _tick(manager, output)

    manager.uncover(held, _view("count"))

    assert _tick(manager, output) == [3] * 4, "two updates before the cover, one after"


def test_a_covered_effects_receipt_still_controls_its_brightness_after_uncovering(
    pack_tree,
) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    held = manager.cover(_view("color"))
    manager.uncover(held, _view("color"))

    receipt.brightness = 0.5

    assert _tick(manager, output) == [0x7F0000] * 4


def test_a_covered_effects_receipt_still_stops_it_after_uncovering(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    held = manager.cover(_view("color"))
    manager.uncover(held, _view("color"))

    receipt.stop()

    assert _tick(manager, output) is None


def test_uncovering_tells_each_output_which_effects_are_restored(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    held = manager.cover(_view("color"))

    manager.uncover(held, _view("color"))

    assert [(keys, r) for keys, _, r in output.restored_calls] == [
        (frozenset({"personal"}), receipt)
    ]


def test_uncovering_restores_the_covered_merge_strategies(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    held = manager.cover(_view("color"))
    manager.set_merge_strategy(Scope.PERSONAL, SPLIT)  # the Overlay's own choice

    manager.uncover(held, _view("color"))

    assert _tick(manager, output) == _ADDITIVE_RED_BLUE


def test_uncovering_resolves_the_covered_view_again(pack_tree) -> None:
    manager, _ = _make_counting_manager(pack_tree)
    held = manager.cover(_view("count"))

    manager.uncover(held, _view("color"))

    manager.set_effect(Scope.PERSONAL, "color.red", {})
    with pytest.raises(UndeclaredPackError):
        manager.set_effect(Scope.PERSONAL, "count.fx", {})


def test_an_effect_whose_receipt_stopped_while_held_is_removed_on_the_next_tick(
    pack_tree,
) -> None:
    manager, output = _make_counting_manager(pack_tree)
    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    held = manager.cover(_view("color"))
    receipt.stop()
    manager.uncover(held, _view("color"))
    output.handle_event_calls.clear()
    output.clear_pixels_calls.clear()

    frame = _tick(manager, output)

    assert frame is None
    assert [call[0].verb for call in output.handle_event_calls] == [EffectVerb.STOP]
    assert output.clear_pixels_calls[0] == "personal"


def test_stacked_covers_each_uncover_their_own_effects(pack_tree) -> None:
    manager, output = _make_counting_manager(pack_tree)
    manager.set_effect(Scope.PERSONAL, "color.red", {})
    under = manager.cover(_view("color"))
    manager.set_effect(Scope.PERSONAL, "color.blue", {})
    middle = manager.cover(_view("color"))

    manager.uncover(middle, _view("color"))
    blue = _tick(manager, output)
    manager.uncover(under, _view("color"))

    assert blue == [0x0000FF] * 4
    assert _tick(manager, output) == [0xFF0000] * 4
