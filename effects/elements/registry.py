"""Registry of all built-in element renderer builders, keyed by element name."""

try:
    from collections.abc import Callable
    from typing import TypeAlias
except ImportError:
    pass

from effects.elements.air import build_air_renderer
from effects.elements.dark import build_dark_renderer
from effects.elements.earth import build_earth_renderer
from effects.elements.fire import build_fire_renderer
from effects.elements.gravity import build_gravity_renderer
from effects.elements.ice import build_ice_renderer
from effects.elements.light import build_light_renderer
from effects.elements.lightning import build_lightning_renderer
from effects.elements.time import build_time_renderer
from effects.elements.water import build_water_renderer
from effects.render import EffectRenderer, RendererConfig

ElementBuilder: TypeAlias = "Callable[[RendererConfig], EffectRenderer]"

ELEMENT_BUILDERS: dict[str, ElementBuilder] = {
    "air": build_air_renderer,
    "dark": build_dark_renderer,
    "earth": build_earth_renderer,
    "fire": build_fire_renderer,
    "gravity": build_gravity_renderer,
    "ice": build_ice_renderer,
    "light": build_light_renderer,
    "lightning": build_lightning_renderer,
    "time": build_time_renderer,
    "water": build_water_renderer,
}


def list_element_names() -> list[str]:
    return list(ELEMENT_BUILDERS.keys())


def get_element_builder(element_name: str) -> ElementBuilder:
    """Return the builder for an element by name, or raise ``ValueError`` if unknown."""
    key = element_name.strip().lower()
    builder = ELEMENT_BUILDERS.get(key)
    if builder is not None:
        return builder

    raise ValueError(
        "Unknown element '"
        + element_name
        + "'. Available: "
        + ", ".join(ELEMENT_BUILDERS.keys())
    )


def build_element_renderer(element_name: str, config: RendererConfig) -> EffectRenderer:
    return get_element_builder(element_name)(config)
