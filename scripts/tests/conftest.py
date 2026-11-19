"""Shared fixtures for scripts/tests."""

import pytest


@pytest.fixture(autouse=True)
def _bypass_mpy_cross_version_check(request, monkeypatch):
    """Bypass the mpy-cross version validation for all deploy tests.

    Skipped for test_mpy_cross_validation.py and for tests named for
    ``version``, so the validation tests run against the real check.
    """
    if "test_mpy_cross_validation" in request.fspath.basename:
        return

    if "version" in request.node.name:
        return

    from scripts import deploy

    monkeypatch.setattr(deploy, "validate_mpy_cross_version", lambda mount: None)
