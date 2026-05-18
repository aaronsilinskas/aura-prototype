from effects.effect import Effect
from effects.palette import PaletteLUT256
from effects.render import EffectRenderer, RendererConfig
from effects.steps.control import call
from engine.effects.manager import EffectBuilder, EffectManager
from engine.effects.scope import Scope
from engine.tests.effects.helpers import SpyEffectOutput, StubEffectBuilder
from engine.timer import Timer


def _make_timer() -> Timer:
    return Timer()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_effect_manager_accepts_builder_and_outputs() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])

    EffectManager(builder=StubEffectBuilder(), outputs=[output])


def test_effect_manager_accepts_empty_outputs_list() -> None:
    EffectManager(builder=StubEffectBuilder(), outputs=[])


# ---------------------------------------------------------------------------
# update — go-dark signal when no effects are active
# ---------------------------------------------------------------------------


def test_update_with_no_effects_sends_go_dark_to_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.update(_make_timer())

    assert output.update_pixels_calls == [[]]


def test_update_with_no_effects_sends_go_dark_to_all_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output_a, output_b])

    manager.update(_make_timer())

    assert output_a.update_pixels_calls == [[]]
    assert output_b.update_pixels_calls == [[]]


def test_update_called_twice_notifies_output_each_tick() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.update(_make_timer())
    manager.update(_make_timer())

    assert len(output.update_pixels_calls) == 2


# ---------------------------------------------------------------------------
# set_effect + update — slice 2
# ---------------------------------------------------------------------------


def test_set_effect_delivers_one_frame_to_matching_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [[output.created_buffers[0]]]


def test_set_effect_nonmatching_output_receives_go_dark() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == [[]]


# ---------------------------------------------------------------------------
# set_effect twice — slice 3
# ---------------------------------------------------------------------------


class _SpyRenderer:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self, state, timer) -> None:
        self.update_count += 1

    def render(self, state, buf) -> None:
        pass


class _SpyEffectBuilder:
    def __init__(self) -> None:
        self.created: list = []

    def __call__(self, name: str, config) -> _SpyRenderer:
        renderer = _SpyRenderer()
        self.created.append(renderer)
        return renderer


def test_set_effect_twice_replaces_effect() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.set_effect(Scope.PERSONAL, "ice", 5, {})
    manager.update(_make_timer())

    assert output.update_pixels_calls == [[output.created_buffers[0]]]


def test_set_effect_twice_first_renderer_not_advanced() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    builder = _SpyEffectBuilder()
    manager = EffectManager(builder=builder, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.set_effect(Scope.PERSONAL, "ice", 5, {})
    manager.update(_make_timer())

    renderer_a = builder.created[0]
    assert renderer_a.update_count == 0


# ---------------------------------------------------------------------------
# out-of-scope go-dark — slice 6
# ---------------------------------------------------------------------------


def test_out_of_scope_output_receives_go_dark_each_frame() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert output_b.update_pixels_calls == [[], []]


# ---------------------------------------------------------------------------
# effect events — slice 8
# ---------------------------------------------------------------------------


class _EventFiringEffectBuilder(EffectBuilder):
    def __init__(self, event_name: str) -> None:
        self._event_name = event_name

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        event_name = self._event_name
        step = call(lambda state, timer: config.notify_listeners(event_name))
        effect = Effect(name).add_steps([step])
        return EffectRenderer(effect, PaletteLUT256(b""))


def test_effect_event_reaches_matching_scope_output() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=_EventFiringEffectBuilder("lightning_strike"), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "shock", 5, {})
    manager.update(_make_timer())

    assert output.handle_event_calls == ["lightning_strike"]


def test_effect_event_does_not_reach_out_of_scope_output() -> None:
    output_a = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        builder=_EventFiringEffectBuilder("lightning_strike"), outputs=[output_a, output_b]
    )

    manager.set_effect(Scope.PERSONAL, "shock", 5, {})
    manager.update(_make_timer())

    assert output_b.handle_event_calls == []


# ---------------------------------------------------------------------------
# resolution — slice 9
# ---------------------------------------------------------------------------


class _CapturingEffectBuilder(EffectBuilder):
    def __init__(self) -> None:
        self.last_config: RendererConfig | None = None

    def __call__(self, name: str, config: RendererConfig) -> EffectRenderer:
        self.last_config = config
        return EffectRenderer(Effect(name), PaletteLUT256(b""))


def test_resolution_equals_max_min_resolution_of_matching_outputs() -> None:
    output_a = SpyEffectOutput(min_resolution=32, scopes=[Scope.PERSONAL])
    output_b = SpyEffectOutput(min_resolution=64, scopes=[Scope.PERSONAL])
    builder = _CapturingEffectBuilder()
    manager = EffectManager(builder=builder, outputs=[output_a, output_b])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})

    assert builder.last_config.resolution == 64


def test_resolution_falls_back_to_16_when_no_outputs_match() -> None:
    builder = _CapturingEffectBuilder()
    manager = EffectManager(builder=builder, outputs=[])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})

    assert builder.last_config.resolution == 16


# ---------------------------------------------------------------------------
# add_effect — slice 4
# ---------------------------------------------------------------------------


def test_add_effect_after_set_effect_delivers_two_frames() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "ice", 5, {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls[0]) == 2


def test_add_effect_both_renderers_advanced_on_each_update() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    builder = _SpyEffectBuilder()
    manager = EffectManager(builder=builder, outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "ice", 5, {})
    manager.update(_make_timer())
    manager.update(_make_timer())

    assert builder.created[0].update_count == 2
    assert builder.created[1].update_count == 2


def test_add_effect_on_empty_scope_delivers_one_frame() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.add_effect(Scope.PERSONAL, "fire", 5, {})
    manager.update(_make_timer())

    assert len(output.update_pixels_calls[0]) == 1


# ---------------------------------------------------------------------------
# stop_effect — slice 5
# ---------------------------------------------------------------------------


def test_stop_effect_causes_go_dark_on_next_update() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls[1] == []


def test_stop_effect_clears_stacked_effects() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    manager = EffectManager(builder=StubEffectBuilder(), outputs=[output])

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.add_effect(Scope.PERSONAL, "ice", 5, {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output.update_pixels_calls[0] == []


def test_stop_effect_does_not_affect_other_scopes() -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        builder=StubEffectBuilder(), outputs=[output_personal, output_directional]
    )

    manager.set_effect(Scope.PERSONAL, "fire", 5, {})
    manager.set_effect(Scope.DIRECTIONAL, "ice", 5, {})
    manager.stop_effect(Scope.PERSONAL)
    manager.update(_make_timer())

    assert output_directional.update_pixels_calls == [[output_directional.created_buffers[0]]]


# ---------------------------------------------------------------------------
# shared renderer dedup — slice 7
# ---------------------------------------------------------------------------


def test_shared_renderer_advanced_once_per_frame_for_composite_scope() -> None:
    output = SpyEffectOutput(min_resolution=10, scopes=[Scope.ALL])
    builder = _SpyEffectBuilder()
    manager = EffectManager(builder=builder, outputs=[output])

    manager.set_effect(Scope.ALL, "fire", 5, {})
    manager.update(_make_timer())

    assert builder.created[0].update_count == 1


def test_each_output_receives_own_buffer_for_composite_scope() -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        builder=StubEffectBuilder(), outputs=[output_personal, output_directional]
    )

    manager.set_effect(Scope.ALL, "fire", 5, {})
    manager.update(_make_timer())

    assert len(output_personal.update_pixels_calls[0]) == 1
    assert len(output_directional.update_pixels_calls[0]) == 1
    personal_buf = output_personal.update_pixels_calls[0][0]
    directional_buf = output_directional.update_pixels_calls[0][0]
    assert personal_buf is not directional_buf


def test_stop_effect_all_sends_go_dark_to_every_output() -> None:
    output_personal = SpyEffectOutput(min_resolution=10, scopes=[Scope.PERSONAL])
    output_directional = SpyEffectOutput(min_resolution=10, scopes=[Scope.DIRECTIONAL])
    manager = EffectManager(
        builder=StubEffectBuilder(), outputs=[output_personal, output_directional]
    )

    manager.set_effect(Scope.ALL, "fire", 5, {})
    manager.update(_make_timer())
    manager.stop_effect(Scope.ALL)
    manager.update(_make_timer())

    assert output_personal.update_pixels_calls[1] == []
    assert output_directional.update_pixels_calls[1] == []
