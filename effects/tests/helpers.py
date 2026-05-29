from effects.render import EffectTimer


def make_timer(elapsed: float) -> EffectTimer:
    """Return an EffectTimer that has already been advanced by ``elapsed`` seconds."""
    t = EffectTimer()
    t.update(elapsed)
    return t
