"""Behaviour-driven tests for the sound, vibration, and IR-transmit components added
by the capacity estimator's #398 model: voice worst-case sizing, the peripheral-count
constraint, the I2C bus model's DRV2605L/LIS3DH terms, and IR-tx's contribution to a
receiver's worst-case frame.

These tests use synthetic board/prop constants (not real hardware numbers) and assert
assignment *decisions* (fits, conflict named, deadline math) rather than the internal
bin-packing algorithm.
"""

import pytest

from scripts.capacity.estimator import assign
from scripts.capacity.profiles import (
    BoardProfile,
    BusBudget,
    EngineComponent,
    IrTransmitComponent,
    McuBaseline,
    PeripheralBudget,
    PixelScopeComponent,
    PropProfile,
    ReceiverComponent,
    SimpleComponent,
    SoundComponent,
    VibrationComponent,
)

# 24 FPS -> frame_budget_ms ~= 41.6667ms
SYNTHETIC_BOARD = BoardProfile(
    name="synthetic-board",
    runtime="circuitpython",
    target_fps=24,
    peripherals=("neopixel", "i2s", "i2c", "pwm"),
    total_free_heap_bytes=200_000,
    engine_host_baseline=McuBaseline(cpu_percent=10.0, heap_bytes=20_000),
    satellite_baseline=McuBaseline(cpu_percent=5.0, heap_bytes=10_000),
    headroom_reserve_percent=20.0,
    bus_budgets={"i2c": BusBudget(bandwidth_bytes_per_sec=10_000)},
    peripheral_budgets={
        "i2s": PeripheralBudget(count=1),
        "i2c": PeripheralBudget(count=1),
        "pwm": PeripheralBudget(count=1),
    },
)


def make_engine(*, remote_mcus: int = 0) -> EngineComponent:
    """Build a synthetic engine component: tick_fixed=2.0, per_rule=0.5, per_event=0.1,
    router_overhead=1.0, with 4 rules and 2 events per tick.
    """
    return EngineComponent(
        name="engine",
        tick_fixed_ms=2.0,
        per_rule_ms=0.5,
        per_event_ms=0.1,
        router_overhead_ms=1.0,
        rules=4,
        events_per_tick=2,
        remote_mcus=remote_mcus,
    )


def make_sound(*, max_concurrent_voices: int, num_voices: int = 4) -> SoundComponent:
    """Build a synthetic shared sound component: mixer_fixed=1.0ms, per_voice=0.5ms."""
    return SoundComponent(
        name="sound",
        mixer_fixed_ms=1.0,
        per_voice_ms=0.5,
        num_voices=num_voices,
        max_concurrent_voices=max_concurrent_voices,
    )


def make_vibration(
    *, max_calls_per_minute: float = 6.0, i2c_transaction_bytes: int = 0
) -> VibrationComponent:
    """Build a synthetic DRV2605L vibration component: cost_ms=0.2 per event."""
    return VibrationComponent(
        name="vibration",
        cost_ms=0.2,
        max_calls_per_minute=max_calls_per_minute,
        i2c_transaction_bytes=i2c_transaction_bytes,
    )


def make_ir_tx(*, blocking_send_ms: float = 5.0) -> IrTransmitComponent:
    """Build a synthetic IR-transmit component: cost_ms=0.1, blocking_send_ms=5.0."""
    return IrTransmitComponent(name="ir-tx", cost_ms=0.1, blocking_send_ms=blocking_send_ms)


def make_ir_rx(
    *,
    buffer_depth: int = 32,
    incoming_rate_hz: float = 1000.0,
    worst_case_frame_ms: float = 10.0,
) -> ReceiverComponent:
    """Build a synthetic IR-rx component modeling `InfraredMultiReceiver`."""
    return ReceiverComponent(
        name="ir-rx",
        cost_ms=0.5,
        base_footprint_bytes=2_000,
        bytes_per_buffer_slot=4,
        buffer_depth=buffer_depth,
        incoming_rate_hz=incoming_rate_hz,
        worst_case_frame_ms=worst_case_frame_ms,
    )


# ---------------------------------------------------------------------------
# Sound: sizing by max concurrent voices, capped by VoicePool.num_voices
# ---------------------------------------------------------------------------


def test_sound_cost_scales_with_max_concurrent_voices():
    """cost_ms = mixer_fixed_ms + per_voice_ms * max_concurrent_voices, below the cap."""
    one_voice = make_sound(max_concurrent_voices=1)
    three_voices = make_sound(max_concurrent_voices=3)

    assert one_voice.cost_ms == pytest.approx(1.0 + 0.5 * 1)
    assert three_voices.cost_ms == pytest.approx(1.0 + 0.5 * 3)


def test_sound_cost_is_capped_at_voice_pool_num_voices():
    """A scene that stacks more voices than VoicePool.num_voices is clamped to the cap --
    VoicePool evicts the oldest voice rather than growing past num_voices."""
    over_cap = make_sound(max_concurrent_voices=10, num_voices=4)

    assert over_cap.effective_voices == 4
    assert over_cap.cost_ms == pytest.approx(1.0 + 0.5 * 4)
    # Cost does not grow further even if max_concurrent_voices keeps climbing.
    even_more = make_sound(max_concurrent_voices=20, num_voices=4)
    assert even_more.cost_ms == over_cap.cost_ms


def test_audio_only_layered_effect_adds_a_voice_but_no_pixel_cost():
    """An audio-only effect (pixels=None, vibration=None) holds a voice -- it counts
    toward max_concurrent_voices for sizing the sound component -- but contributes
    nothing to a pixel scope's cost_ms, which depends only on stack_depth/pixel_count."""
    # Two add_effect layers: one renders pixels, one is audio-only (e.g. a layered
    # stinger). Both hold a voice -> max_concurrent_voices = 2 for sound sizing.
    sound = make_sound(max_concurrent_voices=2)
    assert sound.cost_ms == pytest.approx(1.0 + 0.5 * 2)

    # The pixel scope's stack_depth reflects only the pixel-rendering layer (1), not
    # the audio-only layer -- sound and pixels are sized independently.
    pixel_scope = PixelScopeComponent(
        name="ring",
        driver="neopixel_pwm",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
        stack_depth=1,
    )
    assert pixel_scope.cost_ms == pytest.approx(1 * 0.05 * 10 + 1.0)


def test_sound_component_fits_alongside_engine_on_one_mcu():
    """A modest sound workload co-locates with the engine on the engine-host."""
    engine = make_engine()
    sound = make_sound(max_concurrent_voices=2)
    prop = PropProfile(name="sound-prop", components=[engine, sound])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert len(result.mcus) == 1
    placed = {c.name for c in result.mcus[0].components}
    assert placed == {"engine", "sound"}


# ---------------------------------------------------------------------------
# Peripheral-count constraint
# ---------------------------------------------------------------------------


def test_two_components_requiring_the_single_i2s_is_a_peripheral_conflict():
    """Two components both requiring the board's single I2S peripheral are rejected,
    naming the peripheral constraint."""
    engine = make_engine()
    sound_a = SoundComponent(
        name="sound-a",
        mixer_fixed_ms=1.0,
        per_voice_ms=0.5,
        num_voices=4,
        max_concurrent_voices=1,
    )
    sound_b = SoundComponent(
        name="sound-b",
        mixer_fixed_ms=1.0,
        per_voice_ms=0.5,
        num_voices=4,
        max_concurrent_voices=1,
    )
    prop = PropProfile(name="prop", components=[engine, sound_a, sound_b])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.mcus == []
    assert result.conflict_type == "peripheral"
    assert "i2s" in result.reason


def test_peripheral_conflict_is_checked_before_cpu_and_memory_packing():
    """A peripheral conflict is reported even when CPU/memory would otherwise fit
    comfortably -- the peripheral-count constraint dominates."""
    engine = make_engine()
    # Tiny components -- CPU/memory packing would succeed trivially.
    sound_a = SoundComponent(
        name="sound-a",
        mixer_fixed_ms=0.1,
        per_voice_ms=0.01,
        num_voices=1,
        max_concurrent_voices=1,
    )
    sound_b = SoundComponent(
        name="sound-b",
        mixer_fixed_ms=0.1,
        per_voice_ms=0.01,
        num_voices=1,
        max_concurrent_voices=1,
    )
    prop = PropProfile(name="prop", components=[engine, sound_a, sound_b])

    result = assign(prop, SYNTHETIC_BOARD)

    assert not result.feasible
    assert result.conflict_type == "peripheral"


def test_single_component_requiring_a_peripheral_within_budget_is_feasible():
    """One component requiring the board's single I2C peripheral is feasible."""
    engine = make_engine()
    vibration = make_vibration()
    prop = PropProfile(name="prop", components=[engine, vibration])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None


def test_peripheral_with_no_declared_budget_is_unconstrained():
    """A peripheral with no entry in board.peripheral_budgets is treated as
    unconstrained -- no conflict is raised even if multiple components need it."""
    board_no_budgets = BoardProfile(
        name="no-budgets-board",
        runtime="circuitpython",
        target_fps=24,
        peripherals=("neopixel",),
        total_free_heap_bytes=200_000,
        engine_host_baseline=McuBaseline(cpu_percent=10.0, heap_bytes=20_000),
        satellite_baseline=McuBaseline(cpu_percent=5.0, heap_bytes=10_000),
        headroom_reserve_percent=20.0,
    )
    engine = make_engine()
    sound_a = make_sound(max_concurrent_voices=1)
    sound_b = make_sound(max_concurrent_voices=1)
    prop = PropProfile(name="prop", components=[engine, sound_a, sound_b])

    result = assign(prop, board_no_budgets)

    assert result.feasible
    assert result.conflict_type is None


# ---------------------------------------------------------------------------
# I2C bus model: DRV2605L event-rate + LIS3DH per-frame accelerometer read
# ---------------------------------------------------------------------------


def test_vibration_i2c_bandwidth_derives_from_event_rate():
    """VibrationComponent.i2c_bandwidth_bytes_per_sec = i2c_transaction_bytes *
    (max_calls_per_minute / 60) -- the DRV2605L's average bus contribution."""
    vibration = make_vibration(max_calls_per_minute=12.0, i2c_transaction_bytes=10)

    # 10 bytes * (12/60) = 2 bytes/sec
    assert vibration.i2c_bandwidth_bytes_per_sec == pytest.approx(2.0)


def test_vibration_i2c_bandwidth_is_negligible_but_counted_in_the_bus_budget():
    """The DRV2605L's low event-rate bus share is small but still summed into the
    board's i2c bus budget alongside pixel-scope I2C usage."""
    engine = make_engine()
    vibration = make_vibration(max_calls_per_minute=6.0, i2c_transaction_bytes=10)
    # Matrix scope: 200 bytes * 24 Hz = 4800 bytes/sec.
    matrix_scope = PixelScopeComponent(
        name="panel",
        driver="is31fl3741_matrix",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
        i2c_transaction_bytes=200,
        i2c_frequency_hz=24,
    )
    prop = PropProfile(name="prop", components=[engine, vibration, matrix_scope])

    result = assign(prop, SYNTHETIC_BOARD)

    # 4800 + (10 * 6/60 = 1) = 4801 <= 10_000 budget -- feasible.
    assert result.feasible
    assert result.conflict_type is None


def test_vibration_i2c_bandwidth_can_push_the_bus_over_budget():
    """Adding the DRV2605L's bus share on top of an already-near-budget matrix scope
    can flip the assignment to a bus conflict."""
    engine = make_engine()
    # High event rate + large transaction pushes vibration's own bus share high.
    vibration = make_vibration(max_calls_per_minute=6000.0, i2c_transaction_bytes=200)
    matrix_scope = PixelScopeComponent(
        name="panel",
        driver="is31fl3741_matrix",
        pixel_count=10,
        worst_case_effect_per_pixel_ms=0.05,
        flush_ms=1.0,
        i2c_transaction_bytes=200,
        i2c_frequency_hz=24,
    )
    prop = PropProfile(name="prop", components=[engine, vibration, matrix_scope])

    result = assign(prop, SYNTHETIC_BOARD)

    # matrix: 4800 bytes/sec; vibration: 200 * (6000/60) = 20_000 bytes/sec.
    # 4800 + 20_000 = 24_800 > 10_000 budget -- bus conflict.
    assert not result.feasible
    assert result.conflict_type == "bus"
    assert "i2c" in result.reason


def test_lis3dh_per_frame_read_contributes_i2c_bandwidth():
    """A LIS3DH accelerometer read once per frame contributes
    i2c_transaction_bytes * i2c_frequency_hz to the i2c bus budget."""
    accelerometer = SimpleComponent(
        name="accelerometer", cost_ms=0.1, i2c_transaction_bytes=6, i2c_frequency_hz=24.0
    )

    # 6 bytes * 24 Hz = 144 bytes/sec
    assert accelerometer.i2c_bandwidth_bytes_per_sec == pytest.approx(144.0)


def test_simple_component_off_i2c_bus_contributes_nothing_to_bus_budget():
    """A SimpleComponent with default (zero) i2c fields contributes 0 bandwidth and
    never trips the i2c bus conflict."""
    engine = make_engine()
    renderer = SimpleComponent(name="renderer", cost_ms=1.0)
    accelerometer = SimpleComponent(
        name="accelerometer", cost_ms=0.1, i2c_transaction_bytes=6, i2c_frequency_hz=24.0
    )
    prop = PropProfile(name="prop", components=[engine, renderer, accelerometer])

    result = assign(prop, SYNTHETIC_BOARD)

    assert renderer.i2c_bandwidth_bytes_per_sec == 0
    # 144 bytes/sec is well within the 10_000 bytes/sec budget.
    assert result.feasible
    assert result.conflict_type is None


# ---------------------------------------------------------------------------
# IR transmit: blocking PulseOut.send contributes to worst-case frame time
# ---------------------------------------------------------------------------


def test_ir_tx_blocking_send_alone_does_not_blow_a_receiver_deadline():
    """A receiver whose own worst-case frame is comfortably under its deadline stays
    feasible once a small IR-tx blocking-send contribution is added."""
    engine = make_engine()
    # max_frame_ms = 32 / 1000 * 1000 = 32ms; worst_case_frame_ms = 10ms + 5ms tx = 15ms <= 32ms
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=10.0)
    ir_tx = make_ir_tx(blocking_send_ms=5.0)
    prop = PropProfile(name="prop", components=[engine, ir_rx, ir_tx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None


def test_ir_tx_blocking_send_can_push_a_receivers_worst_case_frame_over_its_deadline():
    """A receiver that would otherwise be within its deadline is rejected once the
    co-located IR-tx component's blocking PulseOut.send is added to its worst-case
    frame -- the soft IR-tx cost still has a real-time effect on the receiver."""
    engine = make_engine()
    # max_frame_ms = 32 / 1000 * 1000 = 32ms; receiver alone: 30ms <= 32ms (feasible alone)
    ir_rx = make_ir_rx(buffer_depth=32, incoming_rate_hz=1000.0, worst_case_frame_ms=30.0)
    without_tx = PropProfile(name="prop", components=[engine, ir_rx])
    without_tx_result = assign(without_tx, SYNTHETIC_BOARD)
    assert without_tx_result.feasible

    # Adding a long blocking send (10ms): 30ms + 10ms = 40ms > 32ms -> deadline conflict.
    ir_tx = make_ir_tx(blocking_send_ms=10.0)
    with_tx = PropProfile(name="prop", components=[engine, ir_rx, ir_tx])
    with_tx_result = assign(with_tx, SYNTHETIC_BOARD)

    assert not with_tx_result.feasible
    assert with_tx_result.conflict_type == "deadline"
    assert "ir-rx" in with_tx_result.reason


def test_ir_tx_with_no_co_located_receiver_has_no_deadline_to_blow():
    """An IR-tx component with no ReceiverComponent in the prop has nothing to check
    its blocking send against -- it is feasible on its own."""
    engine = make_engine()
    ir_tx = make_ir_tx(blocking_send_ms=20.0)
    prop = PropProfile(name="prop", components=[engine, ir_tx])

    result = assign(prop, SYNTHETIC_BOARD)

    assert result.feasible
    assert result.conflict_type is None
