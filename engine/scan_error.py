"""The base of every failure raised while scanning pack roots.

Kept apart from ``engine.pack_catalog`` so ``engine.capabilities``, which the
hardware layer imports, can extend it without importing the scan.
"""

from __future__ import annotations

__all__ = ["PackScanError"]


class PackScanError(ValueError):
    """Base class for every failure raised while scanning pack roots.

    The files on disk are wrong; unrelated to the lookup-time ``RegistryError``
    family, raised after a good scan.
    """
