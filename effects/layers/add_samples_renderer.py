from effects.layers.layer import Layer
from effects.palette import Palette
from effects.render import EffectRenderer, PixelBuffer


class AddSamplesRenderer(EffectRenderer):
    """Blends multiple agents by summing their sample values and applying a single palette.

    Per-pixel: sums ``agent.sample(pos, count)`` across all agents, clamps the
    total to ``1.0``, then maps through a single shared palette.

    The ``state`` argument on ``update`` and ``render`` is accepted for
    signature compatibility with ``EffectRenderer`` but is never read.
    """

    __slots__ = ["_agents", "_name", "_palette"]

    def __init__(self, name: str, agents: list[Layer], palette: Palette) -> None:
        self._name = name
        self._agents = agents
        self._palette = palette

    @property
    def name(self) -> str:
        return self._name

    def update(self, state, timer) -> None:
        """Advance all agents. ``state`` is ignored."""
        elapsed = timer.elapsed
        for agent in self._agents:
            agent.update(elapsed)

    def render(self, state, output: PixelBuffer) -> None:
        """Write additively blended agent colors to ``output``. ``state`` is ignored."""
        count = len(output)
        inv_count = 1.0 / count
        palette = self._palette
        agents = self._agents
        for i in range(count):
            pos = i * inv_count
            total = 0.0
            for agent in agents:
                total += agent.sample(pos, count)
            if total > 1.0:
                total = 1.0
            output[i] = palette.lookup(total)
