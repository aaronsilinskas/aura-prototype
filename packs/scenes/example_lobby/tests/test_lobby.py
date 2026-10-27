"""``example_lobby`` on the Simulation test harness: A steps the selection, B launches it.

Every strip previews one entry, looking ahead from the selection: the first
strip shows the scene B would launch, the next the one after, and so on,
wrapping. The four entries' previews look nothing alike, so a strip's pixels
alone tell which entry it shows.
"""

from __future__ import annotations

from collections.abc import Callable

from app.simulation import TICK, SimulatedDevice, Simulation, Strip
from engine.state import Scope

STRIPS = [
    Scope.PERSONAL,
    Scope.DIRECTIONAL,
    Scope.Global.MAIN,
    Scope.Global.BUFF,
    Scope.Global.DEBUFF,
    Scope.AMBIENT,
]
"""``example_lobby``'s scopes, in look-ahead order."""

RED = 0xFF0000
LIGHTNING_ORANGE = 0xFF6400

WATCH = 1.0
"""How long ``watch_previews`` watches: long enough for lightning to strike at least once."""


def _every_pixel(strip: Strip, test: Callable[[int, int, int], bool]) -> bool:
    return all(test(p >> 16, (p >> 8) & 0xFF, p & 0xFF) for p in strip.pixels)


def _shows_light(strip: Strip) -> bool:
    """White light: every pixel lit, and grey."""
    return _every_pixel(strip, lambda r, g, b: r > 0 and r == g == b)


def _shows_fire(strip: Strip) -> bool:
    """Fire: every pixel lit, red to orange, never blue, and not one solid red."""
    return _every_pixel(strip, lambda r, g, b: r > 0 and b == 0) and not strip.all_lit(RED)


_PREVIEWS: dict[str, Callable[[Strip], bool]] = {
    "hardware_test": lambda strip: strip.shades_of(LIGHTNING_ORANGE),
    "element_browser": _shows_light,
    "red_light_green_light": _shows_fire,
    "tag": lambda strip: strip.all_lit(RED),
}
"""Each entry's preview, as what every frame of it shows.

Lightning flashes orange and goes dark between strikes; a strip dark for the
whole watch shows no entry.
"""


def watch_previews(sim: Simulation, device: SimulatedDevice) -> list[str | None]:
    """Watch every strip for ``WATCH``; return the entry each one previews, in ``STRIPS`` order.

    ``None`` for a strip that shows no one entry throughout.
    """
    candidates = {scope: set(_PREVIEWS) for scope in STRIPS}
    ever_lit = set()
    for _ in range(round(WATCH / TICK)):
        sim.advance(TICK)
        for scope in STRIPS:
            strip = device.strip(scope)
            candidates[scope] &= {scene for scene, shows in _PREVIEWS.items() if shows(strip)}
            if not strip.dark:
                ever_lit.add(scope)
    return [_sole_match(candidates[scope]) if scope in ever_lit else None for scope in STRIPS]


def _sole_match(scenes: set[str]) -> str | None:
    return next(iter(scenes)) if len(scenes) == 1 else None


def test_on_boot_every_strip_previews_from_the_first_entry_wrapping_past_the_last(sim):
    device = sim.add_device("red", scene="example_lobby")

    assert watch_previews(sim, device) == [
        "hardware_test",
        "element_browser",
        "red_light_green_light",
        "tag",
        "hardware_test",
        "element_browser",
    ]


def test_a_steps_the_selection_and_every_strip_follows(sim):
    device = sim.add_device("red", scene="example_lobby")

    device.tap("A")

    assert watch_previews(sim, device) == [
        "element_browser",
        "red_light_green_light",
        "tag",
        "hardware_test",
        "element_browser",
        "red_light_green_light",
    ]


def test_a_on_the_last_entry_wraps_to_the_first(sim):
    device = sim.add_device("red", scene="example_lobby")
    for _ in range(3):  # to tag, the last entry
        device.tap("A")

    device.tap("A")
    device.tap("B")

    assert device.scene == "hardware_test"


def test_b_launches_the_first_entry_before_any_step(sim):
    device = sim.add_device("red", scene="example_lobby")

    device.tap("B")

    assert device.scene == "hardware_test"


def test_b_launches_the_entry_a_stepped_to(sim):
    device = sim.add_device("red", scene="example_lobby")
    device.tap("A")

    device.tap("B")

    assert device.scene == "element_browser"
