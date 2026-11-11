"""Shared fixtures for scripts/tests."""

import pytest


@pytest.fixture(autouse=True)
def _bypass_mpy_cross_version_check(request, monkeypatch):
    """Bypass the mpy-cross version validation for all deploy tests.

    Tests that explicitly test version validation (in test_mpy_cross_validation.py
    and the version-check section of test_deploy.py) opt out by using their own
    ``patch`` calls which shadow this bypass.

    The bypass is applied only to tests outside the dedicated validation test
    module, so the unit-level validation tests run against the real functions.
    """
    if "test_mpy_cross_validation" in request.fspath.basename:
        return

    if "version" in request.node.name:
        return

    from scripts import build

    monkeypatch.setattr(build, "validate_mpy_cross_version", lambda mount, mpy_cross_bin: None)
