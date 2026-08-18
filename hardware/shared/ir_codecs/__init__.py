"""IR wire-frame codec resolution: name -> (ENCODER, DECODER) class pair.

Every concrete codec module in this package (:mod:`hardware.shared.ir_codecs.aura`,
:mod:`hardware.shared.ir_codecs.tag`) exposes module-level ``ENCODER`` /
``DECODER`` attributes -- the convention :func:`codec_for` resolves by name.
Adding a codec is a single, discoverable edit: drop in a module with those two
attributes, no hand-maintained registry to update.

No ``pulseio`` import -- safe on CPython, CircuitPython 10.x, and MicroPython.
"""

import os

from hardware.shared.ir_codecs.base import InfraredDecoder, InfraredEncoder

__all__ = ["UnknownCodecError", "codec_for"]

# This package's dotted import path, used to build each codec's full module
# name (``hardware.shared.ir_codecs.<name>``). ``__name__`` rather than a
# literal so the constant tracks a future package rename for free.
_PACKAGE_NAME = __name__

# Modules under this package that are not themselves codecs: the shared base
# classes (no module-level ENCODER/DECODER) and the package init itself.
_NON_CODEC_MODULES = frozenset({"__init__", "base"})


class UnknownCodecError(ValueError):
    """*name* has no matching module under ``hardware.shared.ir_codecs``.

    Raised by :func:`codec_for`.  A bespoke ``ValueError`` subclass rather
    than the engine's ``UnknownItemError``: ``hardware`` may not import
    ``engine.packs``, where that class lives (the engine <-> hardware
    layering contract is one-way).  Callers classify the failure by
    exception *type*; the message is a free display detail that happens to
    name the known codecs.
    """

    def __init__(self, name: str, available: list[str]) -> None:
        self.name = name
        self.available = available
        super().__init__(f"Unknown IR codec '{name}'. Available: {', '.join(available)}")


def _known_codec_names() -> list[str]:
    """Return the codec names discoverable in this package, alphabetically.

    Dir-scans the package directory rather than consulting a hand-maintained
    list -- the same convention ``engine.packs.scan_item_names`` uses for
    packs/items.  Recognises both ``.py`` (CPython, source deploys) and
    ``.mpy`` (compiled CircuitPython deploys) files, and excludes the
    package's own ``__init__`` and the codec-free ``base`` module.
    """
    package_dir = os.path.dirname(__file__)
    names = set()
    for fname in os.listdir(package_dir):
        if fname.endswith(".mpy"):
            stem = fname[:-4]
        elif fname.endswith(".py"):
            stem = fname[:-3]
        else:
            continue
        if stem in _NON_CODEC_MODULES:
            continue
        names.add(stem)
    return sorted(names)


def codec_for(name: str = "aura") -> tuple[type[InfraredEncoder], type[InfraredDecoder]]:
    """Resolve *name* to its ``(ENCODER, DECODER)`` codec class pair.

    Imports ``hardware.shared.ir_codecs.<name>`` by convention (the same
    dynamic-import mechanism the scene/pack registries use on-device) and
    returns its module-level ``ENCODER`` / ``DECODER`` attributes.  The
    default name (``"aura"``) always resolves.

    Args:
        name: Codec name -- a module in this package, e.g. ``"aura"`` or
            ``"tag"``.

    Returns:
        A ``(EncoderCls, DecoderCls)`` tuple.

    Raises:
        UnknownCodecError: if no ``hardware.shared.ir_codecs.<name>`` module
            exists.  A broken *existing* codec module's own import failure
            propagates unchanged instead of being reported as unknown.
    """
    full_module = f"{_PACKAGE_NAME}.{name}"
    try:
        module = __import__(full_module, None, None, [""])
    except ModuleNotFoundError:
        raise UnknownCodecError(name, _known_codec_names()) from None
    return module.ENCODER, module.DECODER
