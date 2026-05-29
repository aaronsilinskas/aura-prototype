from effects.render import EffectRenderer, PixelBuffer, RendererConfig

# ---------------------------------------------------------------------------
# Stub renderers used by EffectRenderer tests
# ---------------------------------------------------------------------------


class _ConstantRenderer(EffectRenderer):
    """Fills every pixel with a constant packed RGB color."""

    def __init__(self, name: str, color: int) -> None:
        self._name = name
        self._color = color

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        for i in range(len(output)):
            output[i] = self._color


class _SplitRenderer(EffectRenderer):
    """Returns color_low for positions < 0.5 and color_high otherwise."""

    def __init__(self, name: str, color_low: int, color_high: int) -> None:
        self._name = name
        self._color_low = color_low
        self._color_high = color_high

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        pass

    def render(self, output: PixelBuffer) -> None:
        count = len(output)
        for i in range(count):
            output[i] = self._color_high if (i / count) >= 0.5 else self._color_low


class _CountingRenderer(EffectRenderer):
    """Counts how many times update() is called."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.count: int = 0

    @property
    def name(self) -> str:
        return self._name

    def update(self, elapsed: float) -> None:
        self.count += 1

    def render(self, output: PixelBuffer) -> None:
        pass


# ---------------------------------------------------------------------------
# RendererConfig — level clamping
# ---------------------------------------------------------------------------


def test_config_clamps_level_below_one_to_one() -> None:
    config = RendererConfig(level=0, resolution=10)

    assert config.level == 1


def test_config_clamps_level_above_ten_to_ten() -> None:
    config = RendererConfig(level=11, resolution=10)

    assert config.level == 10


def test_config_stores_level_within_valid_range_unchanged() -> None:
    config = RendererConfig(level=5, resolution=10)

    assert config.level == 5


def test_config_stores_options_dict() -> None:
    opts = {"color": "red"}
    config = RendererConfig(level=5, resolution=10, options=opts)

    assert config.options == opts


def test_config_options_defaults_to_empty_dict() -> None:
    config = RendererConfig(level=5, resolution=10)

    assert config.options == {}


# ---------------------------------------------------------------------------
# RendererConfig — resolution clamping
# ---------------------------------------------------------------------------


def test_config_clamps_resolution_below_one_to_one() -> None:
    config = RendererConfig(level=5, resolution=0)

    assert config.resolution == 1


# ---------------------------------------------------------------------------
# RendererConfig — listeners
# ---------------------------------------------------------------------------


def test_notify_listeners_is_silent_when_no_listeners_are_registered() -> None:
    config = RendererConfig(level=5, resolution=10)

    config.notify_listeners("frame_start")  # must not raise


def test_registered_listener_receives_event_on_notify() -> None:
    received: list[str] = []
    config = RendererConfig(
        level=5,
        resolution=10,
        listeners=[received.append],
    )

    config.notify_listeners("frame_start")

    assert received == ["frame_start"]


def test_all_registered_listeners_are_notified_in_registration_order() -> None:
    received: list[str] = []
    config = RendererConfig(
        level=5,
        resolution=10,
        listeners=[
            lambda e: received.append(f"a:{e}"),
            lambda e: received.append(f"b:{e}"),
        ],
    )

    config.notify_listeners("tick")

    assert received == ["a:tick", "b:tick"]


# ---------------------------------------------------------------------------
# RendererConfig — level_lerp
# ---------------------------------------------------------------------------


def test_config_level_lerp_returns_minimum_at_level_one() -> None:
    config = RendererConfig(level=1, resolution=10)

    assert config.level_lerp(0.2, 1.0) == 0.2


def test_config_level_lerp_returns_maximum_at_level_ten() -> None:
    config = RendererConfig(level=10, resolution=10)

    assert config.level_lerp(0.2, 1.0) == 1.0


# ---------------------------------------------------------------------------
# PixelBuffer
# ---------------------------------------------------------------------------


def test_pixel_buffer_count_matches_size_at_construction() -> None:
    buf = PixelBuffer(5)

    assert len(buf) == 5


def test_pixel_buffer_initializes_all_pixels_to_zero() -> None:
    buf = PixelBuffer(4)

    assert list(buf) == [0, 0, 0, 0]


def test_pixel_buffer_setitem_stores_color_at_given_index() -> None:
    buf = PixelBuffer(3)

    buf[1] = 0xFF0000

    assert buf[1] == 0xFF0000


def test_pixel_buffer_iterates_pixels_in_index_order() -> None:
    buf = PixelBuffer(3)
    buf[0] = 0xFF0000
    buf[1] = 0x00FF00
    buf[2] = 0x0000FF

    assert list(buf) == [0xFF0000, 0x00FF00, 0x0000FF]


# ---------------------------------------------------------------------------
# EffectRenderer — base class protocol
# ---------------------------------------------------------------------------


def test_base_renderer_name_raises_not_implemented() -> None:
    import pytest

    renderer = EffectRenderer()
    with pytest.raises(NotImplementedError):
        _ = renderer.name


def test_base_renderer_update_raises_not_implemented() -> None:
    import pytest

    renderer = EffectRenderer()
    with pytest.raises(NotImplementedError):
        renderer.update(0.016)


def test_base_renderer_render_raises_not_implemented() -> None:
    import pytest

    renderer = EffectRenderer()
    with pytest.raises(NotImplementedError):
        renderer.render(PixelBuffer(1))
