import sys

import pytest

from engine.effects.manager import EffectManager
from engine.packs import PackRegistry
from engine.state import Scope
from engine.tests.effects.helpers import CapturingEffectBuilder, SpyEffectBuilder, SpyEffectOutput
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

    assert output.update_pixels_calls == [("personal", [])]


def test_update_with_no_effects_sends_go_dark_to_all_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert output_a.update_pixels_calls == [("personal", [])]
    assert output_b.update_pixels_calls == [("directional", [])]


def test_update_delivers_frames_to_output_on_every_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 2


# ---------------------------------------------------------------------------
# set_effect + update — slice 2
# ---------------------------------------------------------------------------


def test_set_effect_delivers_one_frame_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", [(output.created_buffers[0], receipt)])]


def test_set_effect_nonmatching_output_receives_go_dark(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == [("directional", [])]


# ---------------------------------------------------------------------------
# set_effect twice — slice 3
# ---------------------------------------------------------------------------


def test_set_effect_twice_replaces_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt_ice = manager.set_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [("personal", [(output.created_buffers[1], receipt_ice)])]


def test_set_effect_twice_first_renderer_not_advanced(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    _make_pack(
        pack_env,
        "spy",
        {"fire": _spy_item(), "ice": _spy_item()},
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", 5, {})
    manager.set_effect(Scope.PERSONAL, "spy.ice", 5, {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    manager.update(_make_timer())

    renderer_a = fire_builder.created[0]
    assert renderer_a.update_count == 0


# ---------------------------------------------------------------------------
# out-of-scope go-dark — slice 6
# ---------------------------------------------------------------------------


def test_out_of_scope_output_receives_go_dark_each_frame(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == [("directional", []), ("directional", [])]


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

    receipt = manager.set_effect(Scope.PERSONAL, "events.shock", 5, {})
    manager.update(_make_timer())

    assert output.handle_event_calls == [
        ("shock.start", frozenset({"personal"}), receipt),
        ("lightning_strike", frozenset({"personal"}), receipt),
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

    manager.set_effect(Scope.PERSONAL, "events.shock", 5, {})
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

    manager.set_effect(Scope.PERSONAL, "capture.fire", 5, {})

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

    manager.set_effect(Scope.PERSONAL, "capture.fire", 5, {})

    builder = registry.get("capture", "fire", CapturingEffectBuilder)
    assert builder.last_config.resolution == 16


# ---------------------------------------------------------------------------
# add_effect — slice 4
# ---------------------------------------------------------------------------


def test_add_effect_after_set_effect_delivers_two_frames(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls[0][1]) == 2


def test_add_effect_both_renderers_advanced_on_each_update(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    _make_pack(
        pack_env,
        "spy",
        {"fire": _spy_item(), "ice": _spy_item()},
    )
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "spy.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "spy.ice", 5, {})
    fire_builder = registry.get("spy", "fire", SpyEffectBuilder)
    ice_builder = registry.get("spy", "ice", SpyEffectBuilder)
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert fire_builder.created[0].update_count == 2
    assert ice_builder.created[0].update_count == 2


def test_add_effect_on_empty_scope_delivers_one_frame(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls[0][1]) == 1


def test_frames_for_stacked_effects_are_ordered_oldest_first(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_fire = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt_ice = manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.update(_make_timer())

    _, frames = output.update_pixels_calls[0]
    assert frames[0][1] is receipt_fire
    assert frames[1][1] is receipt_ice


# ---------------------------------------------------------------------------
# stop_effect — slice 5
# ---------------------------------------------------------------------------


def test_stop_effect_causes_go_dark_on_next_update(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls[1][1] == []


def test_stop_effect_clears_stacked_effects(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls[0][1] == []


def test_stop_effect_does_not_affect_other_scopes(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt_ice = manager.set_effect(Scope.DIRECTIONAL, "stub.ice", 5, {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_directional.update_pixels_calls == [
        ("directional", [(output_directional.created_buffers[0], receipt_ice)])
    ]


# ---------------------------------------------------------------------------
# shared renderer dedup — slice 7
# ---------------------------------------------------------------------------


def test_shared_renderer_advanced_once_per_frame_for_composite_scope(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.ALL])
    _make_pack(pack_env, "spy", {"fire": _spy_item()})
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[output])

    manager.set_effect(Scope.ALL, "spy.fire", 5, {})
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

    manager.set_effect(Scope.ALL, "stub.fire", 5, {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls[0][1]) == 1
    assert len(output_directional.update_pixels_calls[0][1]) == 1


def test_each_output_gets_distinct_buffer_for_composite_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", 5, {})
    manager.update(_make_timer())

    personal_buf, _ = output_personal.update_pixels_calls[0][1][0]
    directional_buf, _ = output_directional.update_pixels_calls[0][1][0]
    assert personal_buf is not directional_buf


def test_stop_effect_all_sends_go_dark_to_every_output(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", 5, {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls[1][1] == []
    assert output_directional.update_pixels_calls[1][1] == []


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

    manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    manager.set_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls[0][1]) == 1
    assert len(output_directional.update_pixels_calls[0][1]) == 1
    assert len(output_global.update_pixels_calls[0][1]) == 1


def test_stop_effect_on_partial_scope_continues_rendering_on_remaining_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls[0][1] == []
    assert len(output_directional.update_pixels_calls[0][1]) == 1


def test_stop_effect_with_broader_scope_removes_narrower_effect_completely(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls[0][1] == []
    assert output_directional.update_pixels_calls[0][1] == []


def test_add_effect_does_not_stop_effects_already_running_in_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls[0][1]) == 2
    assert len(output_directional.update_pixels_calls[0][1]) == 1


# ---------------------------------------------------------------------------
# EffectReceipt generation (#63)
# ---------------------------------------------------------------------------


def test_two_add_effect_calls_return_different_receipts(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})

    assert receipt_a is not receipt_b
    assert receipt_a.id != receipt_b.id


# ---------------------------------------------------------------------------
# receipt.stop() + deferred-stop (#64)
# ---------------------------------------------------------------------------


def test_stop_effect_by_receipt_stops_the_matching_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.update_pixels_calls[0][1] == []


def test_stop_effect_by_receipt_leaves_other_effects_running(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    receipt_a.stop()
    manager.update(_make_timer())

    assert len(output.update_pixels_calls[0][1]) == 1


def test_stop_effect_by_receipt_with_stale_receipt_is_silent_noop(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt.stop()
    receipt.stop()  # second call — idempotent
    manager.update(_make_timer())

    assert output.update_pixels_calls[0][1] == []


# ---------------------------------------------------------------------------
# lifecycle events — start/stop (#58)
# ---------------------------------------------------------------------------


def test_add_effect_fires_start_event_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output.handle_event_calls == [("fire.start", frozenset({"personal"}), receipt)]


def test_add_effect_start_event_not_delivered_to_out_of_scope_output(pack_env) -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output_a, output_b])

    manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output_b.handle_event_calls == []


def test_add_effect_does_not_fire_stop_for_existing_effects(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    output.handle_event_calls.clear()

    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})

    assert output.handle_event_calls == [("ice.start", frozenset({"personal"}), ice_receipt)]


def test_add_effect_fires_start_event_unconditionally_for_duplicate_name(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt_a = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt_b = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output.handle_event_calls == [
        ("fire.start", frozenset({"personal"}), receipt_a),
        ("fire.start", frozenset({"personal"}), receipt_b),
    ]


def test_stop_effect_fires_stop_event_to_matching_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [("fire.stop", frozenset({"personal"}), receipt)]


def test_stop_effect_fires_stop_for_each_effect_in_scope(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    ice_receipt = manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    output.handle_event_calls.clear()

    manager.stop_effect(Scope.PERSONAL)

    assert output.handle_event_calls == [
        ("fire.stop", frozenset({"personal"}), fire_receipt),
        ("ice.stop", frozenset({"personal"}), ice_receipt),
    ]


def test_set_effect_fires_stop_then_start_when_replacing_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    output.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", 5, {})

    assert output.handle_event_calls == [
        ("fire.stop", frozenset({"personal"}), fire_receipt),
        ("ice.start", frozenset({"personal"}), ice_receipt),
    ]


def test_set_effect_fires_stop_only_to_outputs_in_call_time_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    ice_receipt = manager.set_effect(Scope.PERSONAL, "stub.ice", 5, {})

    assert output_personal.handle_event_calls == [
        ("fire.stop", frozenset({"personal"}), fire_receipt),
        ("ice.start", frozenset({"personal"}), ice_receipt),
    ]
    assert output_directional.handle_event_calls == []


def test_stop_effect_with_broader_scope_fires_stop_to_all_matching_outputs(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.stop_effect(Scope.ALL)

    assert output_personal.handle_event_calls == [
        ("fire.stop", frozenset({"personal"}), fire_receipt)
    ]
    assert output_directional.handle_event_calls == [
        ("fire.stop", frozenset({"directional"}), fire_receipt)
    ]


def test_stop_effect_by_receipt_fires_stop_event(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    output.handle_event_calls.clear()

    receipt.stop()
    manager.update(_make_timer())

    assert output.handle_event_calls == [("fire.stop", frozenset({"personal"}), receipt)]


def test_stop_effect_by_receipt_only_notifies_outputs_still_serving_the_effect(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    fire_receipt = manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    # set_effect(PERSONAL) narrows fire to DIRECTIONAL and fires fire.stop to PERSONAL
    manager.set_effect(Scope.PERSONAL, "stub.ice", 5, {})
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    # fire is now only on DIRECTIONAL — receipt.stop() should only notify DIRECTIONAL
    fire_receipt.stop()
    manager.update(_make_timer())

    assert output_personal.handle_event_calls == []
    assert output_directional.handle_event_calls == [
        ("fire.stop", frozenset({"directional"}), fire_receipt)
    ]


# ---------------------------------------------------------------------------
# scope forwarding
# ---------------------------------------------------------------------------


def test_handle_event_receives_personal_scope_for_personal_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output.handle_event_calls == [("fire.start", frozenset({"personal"}), receipt)]


def test_handle_event_receives_directional_scope_for_directional_effect(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.DIRECTIONAL, "stub.ice", 5, {})

    assert output.handle_event_calls == [("ice.start", frozenset({"directional"}), receipt)]


def test_handle_event_receives_composite_scope_not_decomposed_leaf(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    receipt = manager.add_effect(Scope.ALL, "stub.fire", 5, {})

    assert output_personal.handle_event_calls == [("fire.start", frozenset({"personal"}), receipt)]
    assert output_directional.handle_event_calls == [
        ("fire.start", frozenset({"directional"}), receipt)
    ]


# ---------------------------------------------------------------------------
# Error cases — malformed effect names
# ---------------------------------------------------------------------------


def test_missing_pack_prefix_raises_value_error() -> None:
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[])

    with pytest.raises(ValueError, match="missing pack prefix"):
        manager.set_effect(Scope.PERSONAL, "fire", 5, {})


def test_unknown_pack_raises_value_error(pack_env) -> None:
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[])

    with pytest.raises(ValueError, match="Unknown effect pack 'spells'"):
        manager.set_effect(Scope.PERSONAL, "spells.fireball", 5, {})


def test_unknown_effect_in_known_pack_raises_value_error(pack_env) -> None:
    _make_pack(pack_env, "elements", {"fire": _stub_item()})
    registry = PackRegistry(item_attr="BUILD")
    registry.scan_dir(str(pack_env), _MODULE_PREFIX)
    manager = EffectManager(registry=registry, outputs=[])

    with pytest.raises(ValueError, match="Unknown effect 'flash' in pack 'elements'"):
        manager.set_effect(Scope.PERSONAL, "elements.flash", 5, {})


# ---------------------------------------------------------------------------
# show_pixels
# ---------------------------------------------------------------------------


def test_update_calls_show_pixels_when_no_effects_are_active() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert len(output.show_pixels_calls) == 1


def test_update_calls_show_pixels_once_per_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.show_pixels_calls) == 3


def test_update_calls_show_pixels_on_all_outputs_each_tick() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert len(output_a.show_pixels_calls) == 1
    assert len(output_b.show_pixels_calls) == 1


# ---------------------------------------------------------------------------
# clear_pixels — issue #139
# ---------------------------------------------------------------------------


def test_stop_effect_calls_clear_pixels_when_last_effect_stops(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.stop_effect(Scope.PERSONAL)

    assert output.clear_pixels_calls == ["personal"]


def test_stop_effect_by_receipt_calls_clear_pixels_when_last_effect_stops(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    receipt.stop()
    manager.update(_make_timer())

    assert output.clear_pixels_calls == ["personal"]


def test_stop_effect_by_receipt_does_not_call_clear_pixels_when_layered_effect_remains(
    pack_env,
) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    fire_receipt = manager.add_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
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

    manager.add_effect(Scope.ALL, "stub.fire", 5, {})
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

    manager.add_effect(Scope.ALL, "stub.fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "stub.ice", 5, {})
    manager.stop_effect(Scope.PERSONAL)

    # fire still covers directional; ice and fire(personal) both stopped
    # personal is now covered by nothing → clear
    # directional still covered by fire → no clear
    assert output_personal.clear_pixels_calls == ["personal"]
    assert output_directional.clear_pixels_calls == []


def test_update_calls_show_pixels_even_when_effects_are_active(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})
    manager.update(_make_timer())

    assert len(output.show_pixels_calls) == 1


def test_update_calls_show_pixels_after_update_pixels_each_tick() -> None:
    call_order: list[str] = []

    class OrderTrackingOutput(SpyEffectOutput):
        def update_pixels(self, scope_key: str, buffers: list, receipts: list) -> None:
            super().update_pixels(scope_key, buffers, receipts)
            call_order.append("update_pixels")

        def show_pixels(self) -> None:
            super().show_pixels()
            call_order.append("show_pixels")

    output = OrderTrackingOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=PackRegistry(item_attr="BUILD"), outputs=[output])

    manager.update(_make_timer())

    assert call_order == ["update_pixels", "show_pixels"]


# ---------------------------------------------------------------------------
# per-key create_buffer
# ---------------------------------------------------------------------------


def test_create_buffer_called_with_scope_key_on_effect_start(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output.create_buffer_key_calls == ["personal"]


def test_create_buffer_called_once_per_matching_key_for_composite_scope(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.ALL, "stub.fire", 5, {})

    assert output_personal.create_buffer_key_calls == ["personal"]
    assert output_directional.create_buffer_key_calls == ["directional"]


def test_create_buffer_not_called_for_out_of_scope_output(pack_env) -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        registry=_make_stub_registry(pack_env),
        outputs=[output_personal, output_directional],
    )

    manager.set_effect(Scope.PERSONAL, "stub.fire", 5, {})

    assert output_directional.create_buffer_key_calls == []


def test_scoped_listener_uses_live_keys_after_scope_narrowing(pack_env) -> None:
    """Renderer-generated events after scope narrowing must reach only remaining-scope outputs."""
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

    manager.add_effect(Scope.ALL, "evt.shock", 5, {})
    manager.stop_effect(Scope.PERSONAL)  # narrows shock: personal key removed
    output_personal.handle_event_calls.clear()
    output_directional.handle_event_calls.clear()

    manager.update(_make_timer())

    # shock renderer fires "lightning_strike"; scoped_listener reads live entry.keys
    # → personal output must NOT receive it after narrowing
    assert not any(c[0] == "lightning_strike" for c in output_personal.handle_event_calls)
    assert any(c[0] == "lightning_strike" for c in output_directional.handle_event_calls)


# ---------------------------------------------------------------------------
# per-key update_pixels
# ---------------------------------------------------------------------------


def test_update_pixels_called_once_per_registered_key_for_multi_key_output(pack_env) -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL, Scope.DIRECTIONAL])
    manager = EffectManager(registry=_make_stub_registry(pack_env), outputs=[output])

    manager.set_effect(Scope.ALL, "stub.fire", 5, {})
    manager.update(_make_timer())

    called_keys = [key for key, _ in output.update_pixels_calls]
    assert set(called_keys) == {"personal", "directional"}
    assert len(called_keys) == 2  # exactly one call per key, no duplicates
