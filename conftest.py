"""Fixtures shared by every test tree: the harness's own tests and every pack's."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from engine.tests.pack_tree import PackTree
from hardware.shared.device_storage import DeviceStorage

if TYPE_CHECKING:
    from app.simulation import Simulation

pytest_plugins = ["pytester"]


@pytest.fixture()
def simulation() -> Iterator[Simulation]:
    """A ``Simulation``, closed after the test so it leaves nothing behind."""
    # Imported here, not at module level, so test trees that never simulate
    # don't load the scene composition layer.
    from app.simulation import Simulation

    with Simulation() as simulation:
        yield simulation


@pytest.fixture()
def pack_tree(tmp_path: Path) -> Iterator[PackTree]:
    """Yield a ``PackTree`` building pack roots under *tmp_path*.

    A scan puts each root's parent on ``sys.path`` and item loads import
    modules under the root's name, so teardown restores ``sys.path`` and
    evicts every module imported under one of the tree's root names.
    """
    tree = PackTree(tmp_path)
    saved_path = list(sys.path)
    known_modules = set(sys.modules)

    yield tree

    for name in list(sys.modules):
        if name not in known_modules and name.split(".")[0] in tree.root_names:
            del sys.modules[name]
    sys.path[:] = saved_path


@pytest.fixture()
def device_storage(tmp_path: Path) -> Iterator[DeviceStorage]:
    """Yield a real ``DeviceStorage`` over a fresh ``card`` directory in *tmp_path*.

    Rooted below *tmp_path* rather than at it, so a host-side file the test
    writes there (an SD-sync pull target) can never be the card's own file.
    ``aura_packs`` is a regular package bound to the first card that carried
    it, so teardown evicts every ``aura_packs*`` module imported during the
    test and drops the card from ``sys.path``, whether or not the test put it
    there.
    """
    card = tmp_path / "card"
    card.mkdir()
    storage = DeviceStorage(str(card))
    known_modules = set(sys.modules)

    yield storage

    for name in list(sys.modules):
        if name not in known_modules and name.split(".")[0] == "aura_packs":
            del sys.modules[name]
    while storage.mount_root in sys.path:
        sys.path.remove(storage.mount_root)
