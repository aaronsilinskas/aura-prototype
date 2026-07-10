import sys
from unittest.mock import ANY

import pytest

from engine.effects.manager import EffectManager
from engine.effects.merge import ADDITIVE, SPLIT
from engine.events import EffectEvent
from engine.packs import PackRegistry
from engine.state import Scope
from engine.tests.effects.helpers import (
    CapturingEffectBuilder,
    RenderLengthProbeEffectBuilder,
    SpyEffectBuilder,
    SpyEffectOutput,
)
from engine.timer import Timer

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_MODULE_PREFIX = "tp"


@pytest.fixture()
def pack_env(tmp_path):
    """Yield a packs-root directory and manage ``sys.path`` / ``sys.modules``."""
    packs_root = tmp_path / _MODULE_PREFIX
    packs_root.mkdir()
    sys.path.insert(0, str(tmp_path))
    known = set(sys.modules)
    yield packs_root
    for key in list(sys.modules):
        if key not in known:
            del sys.modules[key]
    sys.path.remove(str(tmp_path))


def _make_pack(root, name: str, items: dict[str, str]) -> None:
    """Create a pack directory with *items* as ``{item_name: module_content}``."""
    pack_dir = root / name
    pack_dir.mkdir(exist_ok=True)
    (pack_dir / "version.txt").write_text("1.0\n")
    for item, content in items.items():
        (pack_dir / f"{item}.py").write_text(content)


def _stub_item() -> str:
    return (
        "from engine.tests.effects.helpers import StubEffectBuilder\nBUILD = StubEffectBuilder()\n"
    )


def _spy_item() -> str:
    return "from engine.tests.effects.helpers import SpyEffectBuilder\nBUILD = SpyEffectBuilder()\n"


def _make_stub_registry(pack_env) -> PackRegistry:
    """Return a scanned PackRegistry with a 'stub' pack providing common test effects."""
    _make_pack(
        pack_env,
        "stub",
        {"fire": _stub_item(), "ice": _stub_item(), "shock": _stub_item()},
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    return registry


def _make_timer() -> Timer:
    return Timer()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_manager_with_no_outputs_updates_without_error() -> None:
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[])
    manager.update(_make_timer())


# ---------------------------------------------------------------------------
# update — go-dark signal when no effects are active
# ---------------------------------------------------------------------------


def test_update_with_no_effects_sends_go_dark_to_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert output.update_pixels_calls == []
    assert output.clear_pixels_calls == ["personal"]


def test_update_with_no_effects_sends_go_dark_to_all_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert output_a.clear_pixels_calls == ["personal"]
    assert output_b.clear_pixels_calls == ["directional"]


def test_update_sends_go_dark_every_tick_when_no_effects_are_active() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output.clear_pixels_calls == ["personal", "personal"]


def test_update_delivers_one_composed_frame_to_output_on_every_tick(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])
    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 2


# ---------------------------------------------------------------------------
# set_effect + update — slice 2
# ---------------------------------------------------------------------------


def test_set_effect_delivers_one_frame_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[0])]


def test_set_effect_nonmatching_output_receives_go_dark(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == []
    assert output_b.clear_pixels_calls == ["directional"]


# ---------------------------------------------------------------------------
# set_effect twice — slice 3
# ---------------------------------------------------------------------------


def test_set_effect_twice_replaces_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.set_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", output.created_buffers[1])]


def test_set_effect_twice_first_effect_not_advanced(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    _make_pack(
        pack_env,
        "spy",
        {"fire": _spy_item(), "ice": _spy_item()},
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", {})
    manager.set_effect(Scope.PERSONAL, "spy.ice", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    manager.update(_make_timer())

    effect_a = fire_builder.created[0]
    assert effect_a.update_count == 0


# ---------------------------------------------------------------------------
# out-of-scope go-dark — slice 6
# ---------------------------------------------------------------------------


def test_out_of_scope_output_receives_go_dark_each_frame(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == []
    assert output_b.clear_pixels_calls == ["directional", "directional"]


# ---------------------------------------------------------------------------
# effect events — slice 8
# ---------------------------------------------------------------------------


def test_effect_event_reaches_matching_scope_output(pack_env) -> None:
    _make_pack(
        pack_env,
        "events",
        {
            "shock": (
                "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                "BUILD = EventFiringEffectBuilder('lightning_strike')\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])

    receipt = manager.set_effect(Scope.PERSONAL, "events.shock", {})
    manager.update(_make_timer())

    assert output.handle_event_calls == [
        (EffectEvent("events", "shock", "start"), frozenset({"personal"}), ANY, receipt),
        (EffectEvent("events", "shock", "lightning_strike"), frozenset({"personal"}), ANY, receipt),
    ]


def test_effect_event_does_not_reach_out_of_scope_output(pack_env) -> None:
    _make_pack(
        pack_env,
        "events",
        {
            "shock": (
                "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                "BUILD = EventFiringEffectBuilder('lightning_strike')\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=registry, outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "events.shock", {})
    manager.update(_make_timer())

    assert output_b.handle_event_calls == []


# ---------------------------------------------------------------------------
# resolution — slice 9
# ---------------------------------------------------------------------------


def test_resolution_equals_max_min_resolution_of_matching_outputs(pack_env) -> None:
    _make_pack(
        pack_env,
        "capture",
        {
            "fire": (
                "from engine.tests.effects.helpers import CapturingEffectBuilder\n"
                "BUILD = CapturingEffectBuilder()\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output_a = SpyEffectOutput(min_resolution=32, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=64, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "capture.fire", {})

    builder = registry.get("capture", "fire", CapturingEffectBuilder)
    assert builder.last_config.resolution == 64


def test_resolution_falls_back_to_default_when_no_outputs_match(pack_env) -> None:
    _make_pack(
        pack_env,
        "capture",
        {
            "fire": (
                "from engine.tests.effects.helpers import CapturingEffectBuilder\n"
                "BUILD = CapturingEffectBuilder()\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[])

    manager.set_effect(Scope.PERSONAL, "capture.fire", {})

    builder = registry.get("capture", "fire", CapturingEffectBuilder)
    assert builder.last_config.resolution == 16


# ---------------------------------------------------------------------------
# add_effect — slice 4
# ---------------------------------------------------------------------------


def test_add_effect_after_set_effect_delivers_a_single_composed_frame(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_add_effect_both_effects_advanced_on_each_update(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    _make_pack(
        pack_env,
        "spy",
        {"fire": _spy_item(), "ice": _spy_item()},
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", {})
    manager.add_effect(Scope.PERSONAL, "spy.ice", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    ice_builder = registry.get("spy", "ice", SpyEffectBuilder)
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert fire_builder.created[0].update_count == 2
    assert ice_builder.created[0].update_count == 2


def test_add_effect_on_empty_scope_delivers_one_frame(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_add_effect_layers_split_two_effects_side_by_side_in_one_buffer(pack_env) -> None:
    """Split routing: layering two effects on one scope shows both, oldest-first,

    each in its own contiguous slice of the composed region -- not just the
    topmost effect.
    """
    _make_pack(
        pack_env,
        "color",
        {
            "red": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
            ),
            "blue": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
            ),
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])

    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.update(_make_timer())

    _, composed = output.update_pixels_calls[0]
    assert list(composed) == [0xFF0000] * 5 + [0x0000FF] * 5


def test_render_runs_after_merge_strategy_sizes_the_buffer(pack_env) -> None:
    """Split's prepare_buffers partitions each buffer before an effect renders into it."""
    _make_pack(
        pack_env,
        "probe",
        {
            "beam": (
                "from engine.tests.effects.helpers import RenderLengthProbeEffectBuilder\n"
                "BUILD = RenderLengthProbeEffectBuilder()\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])

    manager.add_effect(Scope.PERSONAL, "probe.beam", {})
    manager.add_effect(Scope.PERSONAL, "probe.beam", {})
    manager.update(_make_timer())

    builder = registry.get("probe", "beam", RenderLengthProbeEffectBuilder)
    assert builder.observed_lengths == [5, 5]


# ---------------------------------------------------------------------------
# stop_effect — slice 5
# ---------------------------------------------------------------------------


def test_stop_effect_causes_go_dark_on_next_update(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1
    assert output.clear_pixels_calls[-1] == "personal"


def test_stop_effect_clears_stacked_effects(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_stop_effect_does_not_affect_other_scopes(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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


def test_shared_effect_advanced_once_per_frame_for_composite_scope(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.ALL])
    _make_pack(pack_env, "spy", {"fire": _spy_item()})
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.ALL, "spy.fire", {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    manager.update(_make_timer())

    assert fire_builder.created[0].update_count == 1


def test_each_output_receives_one_frame_for_composite_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1


def test_each_output_gets_distinct_buffer_for_composite_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    _, personal_buf = output_personal.update_pixels_calls[0]
    _, directional_buf = output_directional.update_pixels_calls[0]
    assert personal_buf is not directional_buf


def test_stop_effect_all_sends_go_dark_to_every_output(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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


def test_set_effect_on_partial_scope_leaves_other_scope_effects_running(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    output_global = SpyEffectOutput(min_resolution=10, scopes=[Scope.Global.MAIN])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional, output_global],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.set_effect(Scope.PERSONAL, "stub.ice", {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls) == 1
    assert len(output_directional.update_pixels_calls) == 1
    assert len(output_global.update_pixels_calls) == 1


def test_stop_effect_on_partial_scope_continues_rendering_on_remaining_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls == []
    assert len(output_directional.update_pixels_calls) == 1


def test_stop_effect_with_broader_scope_removes_narrower_effect_completely(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls == []
    assert output_directional.update_pixels_calls == []


def test_add_effect_does_not_stop_effects_already_running_in_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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


def test_two_add_effect_calls_return_different_receipts(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.ice", {})

    assert receipt_a is not receipt_b
    assert receipt_a.id != receipt_b.id


# ---------------------------------------------------------------------------
# receipt.stop() + deferred-stop (#64)
# ---------------------------------------------------------------------------


def test_stop_effect_by_receipt_stops_the_matching_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_stop_effect_by_receipt_leaves_other_effects_running(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    receipt_a.stop()
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 1


def test_stop_effect_by_receipt_with_stale_receipt_is_silent_noop(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    receipt.stop()  # second call — idempotent
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


# ---------------------------------------------------------------------------
# lifecycle events — start/stop (#58)
# ---------------------------------------------------------------------------


def test_add_effect_fires_start_event_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "start"), frozenset({"personal"}), ANY, receipt)
    ]


def test_add_effect_start_event_not_delivered_to_out_of_scope_output(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output_b.handle_event_calls == []


def test_add_effect_does_not_fire_stop_for_existing_effects(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "ice", "start"), frozenset({"personal"}), ANY, ice_receipt)
    ]


def test_add_effect_fires_start_event_unconditionally_for_duplicate_name(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "start"), frozenset({"personal"}), ANY, receipt_a),
        (EffectEvent("stub", "fire", "start"), frozenset({"personal"}), ANY, receipt_b),
    ]


def test_stop_effect_fires_stop_event_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, receipt)
    ]


def test_stop_effect_fires_stop_for_each_effect_in_scope(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", "stop"), frozenset({"personal"}), ANY, ice_receipt),
    ]


def test_set_effect_fires_stop_then_start_when_replacing_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", "start"), frozenset({"personal"}), ANY, ice_receipt),
    ]


def test_set_effect_fires_stop_only_to_outputs_in_call_time_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.ALL, "stub.fire", {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", {})

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, fire_receipt),
        (EffectEvent("stub", "ice", "start"), frozenset({"personal"}), ANY, ice_receipt),
    ]
    assert output_directional.handle_event_calls == []


def test_stop_effect_with_broader_scope_fires_stop_to_all_matching_outputs(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.stop_effect(Scope.ALL)

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, fire_receipt)
    ]
    assert output_directional.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"directional"}), ANY, fire_receipt)
    ]


def test_stop_effect_by_receipt_fires_stop_event(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    output.handle_event_calls.clear()

    receipt.stop()
    manager.update(_make_timer())

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "stop"), frozenset({"personal"}), ANY, receipt)
    ]


def test_stop_effect_by_receipt_only_notifies_outputs_still_serving_the_effect(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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
        (EffectEvent("stub", "fire", "stop"), frozenset({"directional"}), ANY, fire_receipt)
    ]


# ---------------------------------------------------------------------------
# scope forwarding
# ---------------------------------------------------------------------------


def test_handle_event_receives_personal_scope_for_personal_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "fire", "start"), frozenset({"personal"}), ANY, receipt)
    ]


def test_handle_event_receives_directional_scope_for_directional_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.DIRECTIONAL, "stub.ice", {})

    assert output.handle_event_calls == [
        (EffectEvent("stub", "ice", "start"), frozenset({"directional"}), ANY, receipt)
    ]


def test_handle_event_receives_composite_scope_not_decomposed_leaf(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    receipt = manager.add_effect(Scope.ALL, "stub.fire", {})

    assert output_personal.handle_event_calls == [
        (EffectEvent("stub", "fire", "start"), frozenset({"personal"}), ANY, receipt)
    ]
    assert output_directional.handle_event_calls == [
        (EffectEvent("stub", "fire", "start"), frozenset({"directional"}), ANY, receipt)
    ]


# ---------------------------------------------------------------------------
# Error cases — malformed effect names
# ---------------------------------------------------------------------------


def test_missing_pack_prefix_raises_value_error() -> None:
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[])

    with pytest.raises(ValueError, match="missing pack prefix"):
        manager.set_effect(Scope.PERSONAL, "fire", {})


def test_unknown_pack_raises_value_error(pack_env) -> None:
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[])

    with pytest.raises(ValueError, match="Unknown effect pack 'spells'"):
        manager.set_effect(Scope.PERSONAL, "spells.fireball", {})


def test_unknown_effect_in_known_pack_raises_value_error(pack_env) -> None:
    _make_pack(pack_env, "elements", {"fire": _stub_item()})
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[])

    with pytest.raises(ValueError, match="Unknown effect 'flash' in pack 'elements'"):
        manager.set_effect(Scope.PERSONAL, "elements.flash", {})


# ---------------------------------------------------------------------------
# flush
# ---------------------------------------------------------------------------


def test_update_calls_flush_when_no_effects_are_active() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_update_calls_flush_once_per_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.flush_calls) == 3


def test_update_calls_flush_on_all_outputs_each_tick() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert len(output_a.flush_calls) == 1
    assert len(output_b.flush_calls) == 1


# ---------------------------------------------------------------------------
# clear_pixels — issue #139
# ---------------------------------------------------------------------------


def test_stop_effect_calls_clear_pixels_when_last_effect_stops(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)

    assert output.clear_pixels_calls == ["personal"]


def test_stop_effect_by_receipt_calls_clear_pixels_when_last_effect_stops(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.clear_pixels_calls[0] == "personal"


def test_stop_effect_by_receipt_does_not_call_clear_pixels_when_layered_effect_remains(
    pack_env,
) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", {})
    fire_receipt.stop()
    manager.update(_make_timer())

    assert output.clear_pixels_calls == []


def test_clear_pixels_fires_for_narrowed_key_with_no_remaining_coverage(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", {})
    manager.stop_effect(Scope.PERSONAL)

    assert output_personal.clear_pixels_calls == ["personal"]
    assert output_directional.clear_pixels_calls == []


def test_clear_pixels_not_fired_for_key_still_covered_after_narrowing(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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


def test_update_calls_flush_even_when_effects_are_active(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_update_calls_flush_after_update_pixels_each_tick(pack_env) -> None:
    call_order: list[str] = []

    class OrderTrackingOutput(SpyEffectOutput):
        def update_pixels(self, scope_key: str, buffer) -> None:
            super().update_pixels(scope_key, buffer)
            call_order.append("update_pixels")

        def flush(self) -> None:
            super().flush()
            call_order.append("flush")

    output = OrderTrackingOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

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
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert call_order == ["clear_pixels", "flush"]


# ---------------------------------------------------------------------------
# per-key create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_called_with_scope_key_on_effect_start(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.create_buffer_key_calls == ["personal"]


def test_create_buffer_called_once_per_matching_key_for_composite_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", {})

    assert output_personal.create_buffer_key_calls == ["personal"]
    assert output_directional.create_buffer_key_calls == ["directional"]


def test_create_buffer_not_called_for_out_of_scope_output(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output_directional.create_buffer_key_calls == []


def test_scoped_listener_uses_live_keys_after_scope_narrowing(pack_env) -> None:
    """Effect-triggered events after scope narrowing must reach only remaining-scope outputs."""
    _make_pack(
        pack_env,
        "evt",
        {
            "shock": (
                "from engine.tests.effects.helpers import EventFiringEffectBuilder\n"
                "BUILD = EventFiringEffectBuilder('lightning_strike')\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=registry, outputs=[output_personal, output_directional])

    manager.add_effect(Scope.ALL, "evt.shock", {})
    manager.stop_effect(Scope.PERSONAL)  # narrows shock: personal key removed
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.update(_make_timer())

    # shock effect fires "lightning_strike"; scoped_listener reads live entry.keys
    # → personal output must NOT receive it after narrowing
    assert not any(
        c[0] == EffectEvent("evt", "shock", "lightning_strike")
        for c in output_personal.handle_event_calls
    )
    assert any(
        c[0] == EffectEvent("evt", "shock", "lightning_strike")
        for c in output_directional.handle_event_calls
    )


# ---------------------------------------------------------------------------
# per-key update_pixels
# ---------------------------------------------------------------------------


def test_update_pixels_called_once_per_registered_key_for_multi_key_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL, Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.ALL, "stub.fire", {})
    manager.update(_make_timer())

    called_keys = [key for key, _ in output.update_pixels_calls]
    assert set(called_keys) == {"personal", "directional"}
    assert len(called_keys) == 2  # exactly one call per key, no duplicates


# ---------------------------------------------------------------------------
# receives_pixels — issue #191
# ---------------------------------------------------------------------------


def test_output_with_receives_pixels_false_gets_no_create_buffer(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert output.create_buffer_key_calls == []


def test_output_with_receives_pixels_false_gets_no_update_pixels(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == []


def test_output_with_receives_pixels_false_still_gets_flush(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output.flush_calls) == 1


def test_output_with_receives_pixels_false_flush_called_even_with_no_effects() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False)
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert len(output.flush_calls) == 1
    assert output.update_pixels_calls == []


def test_pixel_output_alongside_non_pixel_output_both_get_flush(pack_env) -> None:
    pixel_output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    non_pixel_output = SpyEffectOutput(
        min_resolution=10, scopes=[Scope.PERSONAL], receives_pixels=False
    )
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
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


def test_effect_with_renders_pixels_false_skips_buffer_allocation(pack_env) -> None:
    _make_pack(
        pack_env,
        "nopix",
        {
            "event": (
                "from effects.effect import Effect, EffectConfig\n"
                "from engine.effects.manager import EffectBuilder\n"
                "class _Builder(EffectBuilder):\n"
                "    def __call__(self, name, config): return Effect(name=name)\n"
                "BUILD = _Builder()\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)

    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "nopix.event", {})

    assert output.create_buffer_key_calls == []


def test_effect_with_renders_pixels_false_skips_update_pixels_but_calls_flush(pack_env) -> None:
    _make_pack(
        pack_env,
        "nopix",
        {
            "event": (
                "from effects.effect import Effect, EffectConfig\n"
                "from engine.effects.manager import EffectBuilder\n"
                "class _Builder(EffectBuilder):\n"
                "    def __call__(self, name, config): return Effect(name=name)\n"
                "BUILD = _Builder()\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)

    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "nopix.event", {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == []
    assert output.clear_pixels_calls == ["personal"]
    assert len(output.flush_calls) == 1


# ---------------------------------------------------------------------------
# EffectReceipt — brightness and loudness from options (#249)
# ---------------------------------------------------------------------------


def test_set_effect_receipt_brightness_defaults_to_one(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert receipt.brightness == 1.0


def test_set_effect_receipt_loudness_defaults_to_one(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {})

    assert receipt.loudness == 1.0


def test_set_effect_transfers_brightness_from_options(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {"brightness": 0.5})

    assert receipt.brightness == 0.5


def test_set_effect_transfers_loudness_from_options(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", {"loudness": 0.25})

    assert receipt.loudness == 0.25


def test_add_effect_transfers_brightness_from_options(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", {"brightness": 0.75})

    assert receipt.brightness == 0.75


def test_set_effect_rejects_out_of_range_brightness_option(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "stub.fire", {"brightness": 1.5})


def test_set_effect_rejects_out_of_range_loudness_option(pack_env) -> None:
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[])

    with pytest.raises(ValueError):
        manager.set_effect(Scope.PERSONAL, "stub.fire", {"loudness": -0.1})


# ---------------------------------------------------------------------------
# set_merge_strategy — issue #587
# ---------------------------------------------------------------------------


def test_set_merge_strategy_takes_effect_starting_next_tick(pack_env) -> None:
    """Switching from Split to Additive mid-run blends from the very next tick onward."""
    _make_pack(
        pack_env,
        "color",
        {
            "red": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
            ),
            "blue": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
            ),
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])
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


def test_set_merge_strategy_leaves_other_scopes_strategy_unchanged(pack_env) -> None:
    _make_pack(
        pack_env,
        "color",
        {
            "red": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
            ),
            "blue": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
            ),
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
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


def test_two_outputs_sharing_scope_both_receive_frame_on_update(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_a, output_b],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    assert len(output_a.update_pixels_calls) == 1
    assert len(output_b.update_pixels_calls) == 1


def test_two_outputs_sharing_scope_each_gets_its_own_buffer(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_a, output_b],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", {})
    manager.update(_make_timer())

    _, buf_a = output_a.update_pixels_calls[0]
    _, buf_b = output_b.update_pixels_calls[0]
    assert buf_a is not buf_b


def test_two_outputs_sharing_scope_both_reflect_the_same_receipts_brightness(pack_env) -> None:
    _make_pack(
        pack_env,
        "color",
        {
            "red": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
            )
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output_a = SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=4, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output_a, output_b])

    receipt = manager.set_effect(Scope.PERSONAL, "color.red", {})
    receipt.brightness = 0.5
    manager.update(_make_timer())

    _, buf_a = output_a.update_pixels_calls[0]
    _, buf_b = output_b.update_pixels_calls[0]
    assert list(buf_a) == list(buf_b) == [0x7F0000] * 4


# ---------------------------------------------------------------------------
# reset_merge_strategies / capture_merge_strategies / apply_merge_strategies
# — the EffectAdmin face's pointwise merge-strategy operations (issue #638)
# ---------------------------------------------------------------------------


def test_capture_merge_strategies_defaults_every_registered_key_to_split() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL, Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    assert manager.capture_merge_strategies() == {"personal": SPLIT, "directional": SPLIT}


def test_capture_merge_strategies_returns_a_copy_independent_of_later_live_map_mutations() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    snapshot = manager.capture_merge_strategies()
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)

    assert snapshot["personal"] is SPLIT, "earlier snapshot must not see the later mutation"


def test_reset_merge_strategies_sets_every_registered_key_back_to_split() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL, Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    manager.set_merge_strategy(Scope.DIRECTIONAL, ADDITIVE)

    manager.reset_merge_strategies()

    assert manager.capture_merge_strategies() == {"personal": SPLIT, "directional": SPLIT}


def test_apply_merge_strategies_installs_the_given_snapshot_as_the_live_map() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    snapshot = {"personal": SPLIT}

    manager.apply_merge_strategies(snapshot)

    assert manager.capture_merge_strategies() == snapshot


def test_apply_merge_strategies_takes_effect_on_the_very_next_tick(pack_env) -> None:
    """Direct-installing a captured Split snapshot over a live Additive choice
    must change the composed pixels from the very next update()."""
    _make_pack(
        pack_env,
        "color",
        {
            "red": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0xFF0000)\n"
            ),
            "blue": (
                "from engine.tests.effects.helpers import ColorFillEffectBuilder\n"
                "BUILD = ColorFillEffectBuilder(0x0000FF)\n"
            ),
        },
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=registry, outputs=[output])
    split_snapshot = manager.capture_merge_strategies()
    manager.add_effect(Scope.PERSONAL, "color.red", {})
    manager.add_effect(Scope.PERSONAL, "color.blue", {})
    manager.set_merge_strategy(Scope.PERSONAL, ADDITIVE)
    manager.update(_make_timer())
    _, additive_composed = output.update_pixels_calls[-1]
    assert list(additive_composed) == [0xFF00FF] * 10

    manager.apply_merge_strategies(split_snapshot)
    manager.update(_make_timer())

    _, split_composed = output.update_pixels_calls[-1]
    assert list(split_composed) == [0xFF0000] * 5 + [0x0000FF] * 5
