"""Unit tests for packs.scenes.tag.effects.ready."""

from __future__ import annotations

from effects.effect import EffectConfig, PixelBuffer
from packs.scenes.tag.effects.ready import BUILD


def _config(options: dict | None = None) -> EffectConfig:
    return EffectConfig(resolution=16, options=options or {})


def _build(options: dict | None = None):
    return BUILD("scene.ready", _config(options))


def _brightest_index(buf: PixelBuffer) -> int:
    """Return the index of the pixel with the largest red channel."""
    return max(range(len(buf)), key=lambda i: (buf[i] >> 16) & 0xFF)


def test_ready_shows_a_red_laser() -> None:
    effect = _build()
    effect.pixels.update(0.0)
    buf = PixelBuffer(30)
    effect.pixels.render(buf)

    # Some pixels are lit...
    assert any(p != 0x000000 for p in buf)
    # ...and every lit pixel is pure red (no green or blue channel).
    assert all((p & 0x00FFFF) == 0 for p in buf)


def test_ready_laser_rotates_across_the_strip() -> None:
    effect = _build()
    buf = PixelBuffer(30)

    effect.pixels.update(0.1)
    effect.pixels.render(buf)
    first_peak = _brightest_index(buf)

    effect.pixels.update(0.4)
    effect.pixels.render(buf)
    second_peak = _brightest_index(buf)

    assert first_peak != second_peak


def test_ready_rotate_speed_is_configurable() -> None:
    slow = _build({"rotate_speed": 0.1})
    fast = _build({"rotate_speed": 1.0})
    slow_buf = PixelBuffer(30)
    fast_buf = PixelBuffer(30)

    slow.pixels.update(0.25)
    slow.pixels.render(slow_buf)
    fast.pixels.update(0.25)
    fast.pixels.render(fast_buf)

    # The faster laser has swept further, so its bright peak sits elsewhere.
    assert _brightest_index(slow_buf) != _brightest_index(fast_buf)


def test_ready_has_no_audio() -> None:
    effect = _build()

    assert effect.audio is None
