"""Fixtures shared by every test tree."""

import sys

import pytest

from hardware.shared.device_storage import DeviceStorage

pytest_plugins = ["pytester"]


@pytest.fixture
def device_storage(tmp_path):
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
