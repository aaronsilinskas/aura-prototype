from effects.effect import PixelBuffer
from engine.effects.merge import ADDITIVE, SPLIT
from engine.state import EffectReceipt


def _buffer(colors: list[int], capacity: int | None = None) -> PixelBuffer:
    """Build a full-capacity PixelBuffer pre-loaded with *colors*."""
    buf = PixelBuffer(capacity if capacity is not None else len(colors))
    for i, color in enumerate(colors):
        buf[i] = color
    return buf


def _receipt(brightness: float) -> EffectReceipt:
    receipt = EffectReceipt(1)
    receipt.brightness = brightness
    return receipt


# ---------------------------------------------------------------------------
# SplitMerge.prepare_buffers — partitioning
# ---------------------------------------------------------------------------


def test_split_prepare_buffers_gives_single_buffer_the_full_region() -> None:
    buffers = [PixelBuffer(6)]

    SPLIT.prepare_buffers(buffers)

    assert len(buffers[0]) == 6


def test_split_prepare_buffers_divides_evenly_sized_region_equally() -> None:
    buffers = [PixelBuffer(6), PixelBuffer(6)]

    SPLIT.prepare_buffers(buffers)

    assert [len(b) for b in buffers] == [3, 3]


def test_split_prepare_buffers_gives_remainder_pixels_to_first_parts() -> None:
    buffers = [PixelBuffer(7), PixelBuffer(7), PixelBuffer(7)]

    SPLIT.prepare_buffers(buffers)

    assert [len(b) for b in buffers] == [3, 2, 2]


def test_split_prepare_buffers_zero_sizes_surplus_when_more_buffers_than_pixels() -> None:
    buffers = [PixelBuffer(2), PixelBuffer(2), PixelBuffer(2)]

    SPLIT.prepare_buffers(buffers)

    assert [len(b) for b in buffers] == [1, 1, 0]


# ---------------------------------------------------------------------------
# SplitMerge.merge — compositing
# ---------------------------------------------------------------------------


def test_split_merge_of_single_buffer_is_bit_identical_at_full_brightness() -> None:
    buf = _buffer([0x010203, 0x040506, 0x070809])
    buf.resize(3)

    result = SPLIT.merge([buf], [_receipt(1.0)])

    assert list(result) == [0x010203, 0x040506, 0x070809]
    assert len(result) == 3


def test_split_merge_places_each_part_at_its_partitioned_offset() -> None:
    low = _buffer([0xFF0000, 0x00FF00], capacity=4)
    low.resize(2)
    high = _buffer([0x0000FF, 0x0000FF], capacity=4)
    high.resize(2)

    result = SPLIT.merge([low, high], [_receipt(1.0), _receipt(1.0)])

    assert list(result) == [0xFF0000, 0x00FF00, 0x0000FF, 0x0000FF]
    assert len(result) == 4


def test_split_merge_scales_each_part_by_its_own_receipt_brightness() -> None:
    a = _buffer([0x646464], capacity=2)  # 100, 100, 100
    a.resize(1)
    b = _buffer([0x646464], capacity=2)
    b.resize(1)

    result = SPLIT.merge([a, b], [_receipt(1.0), _receipt(0.5)])

    assert list(result) == [0x646464, 0x323232]  # 100 unscaled, 50 at half brightness


def test_split_merge_treats_missing_receipt_as_full_brightness() -> None:
    buf = _buffer([0x646464])
    buf.resize(1)

    result = SPLIT.merge([buf], [None])

    assert list(result) == [0x646464]


# ---------------------------------------------------------------------------
# AdditiveMerge.prepare_buffers — full-width sizing
# ---------------------------------------------------------------------------


def test_additive_prepare_buffers_sizes_every_buffer_to_full_region_width() -> None:
    buffers = [PixelBuffer(5), PixelBuffer(5), PixelBuffer(5)]

    ADDITIVE.prepare_buffers(buffers)

    assert [len(b) for b in buffers] == [5, 5, 5]


def test_additive_prepare_buffers_restores_full_width_after_split_left_it_partitioned() -> None:
    buffers = [PixelBuffer(6), PixelBuffer(6)]
    SPLIT.prepare_buffers(buffers)
    assert [len(b) for b in buffers] == [3, 3]  # sanity check on the prior strategy's effect

    ADDITIVE.prepare_buffers(buffers)

    assert [len(b) for b in buffers] == [6, 6]


# ---------------------------------------------------------------------------
# AdditiveMerge.merge — blending
# ---------------------------------------------------------------------------


def test_additive_merge_of_single_buffer_is_bit_identical_to_split_single_buffer_result() -> None:
    additive_buf = _buffer([0x010203, 0x040506])
    split_buf = _buffer([0x010203, 0x040506])

    additive_result = ADDITIVE.merge([additive_buf], [_receipt(1.0)])
    split_result = SPLIT.merge([split_buf], [_receipt(1.0)])

    assert list(additive_result) == list(split_result)


def test_additive_merge_sums_channels_across_buffers() -> None:
    red = _buffer([0x640000])  # r=100
    green = _buffer([0x006400])  # g=100

    result = ADDITIVE.merge([red, green], [_receipt(1.0), _receipt(1.0)])

    assert list(result) == [0x646400]  # r=100, g=100 combined, no overlap so no clamping


def test_additive_merge_clamps_summed_channel_to_255() -> None:
    bright_a = _buffer([0xC80000])  # r=200
    bright_b = _buffer([0xC80000])  # r=200

    result = ADDITIVE.merge([bright_a, bright_b], [_receipt(1.0), _receipt(1.0)])

    assert list(result) == [0xFF0000]  # 200 + 200 clamps to 255, not 400


def test_additive_merge_scales_each_buffer_by_its_own_receipt_brightness_before_blending() -> None:
    a = _buffer([0x640000])  # r=100
    b = _buffer([0x640000])  # r=100

    result = ADDITIVE.merge([a, b], [_receipt(1.0), _receipt(0.5)])

    assert list(result) == [0x960000]  # 100 + 50 (100 scaled by 0.5) = 150 = 0x96


def test_additive_merge_treats_missing_receipt_as_full_brightness() -> None:
    a = _buffer([0x640000])
    b = _buffer([0x640000])

    result = ADDITIVE.merge([a, b], [None, None])

    assert list(result) == [0xC80000]  # 100 + 100, neither scaled down
