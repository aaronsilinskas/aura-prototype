"""Fixtures shared by the Composition layer's tests."""

from collections.abc import Iterator

import pytest

from app.tests.probe import HEARD, Probe
from hardware.shared.device_storage import DeviceStorage


@pytest.fixture()
def probe(device_storage: DeviceStorage) -> Iterator[Probe]:
    """Yield a ``Probe`` writing its scene onto the ``device_storage`` card.

    ``device_storage`` evicts the card modules the boot imports; teardown here
    clears what the probe's rule recorded.
    """
    yield Probe(device_storage)
    HEARD.clear()
